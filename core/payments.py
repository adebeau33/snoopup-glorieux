import requests
from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Event,Registration,Order,OrderLine,Ticket,Job,Audit

def create_order(buyer,event,registration_ids):
 if not buyer.verified:raise ValidationError('Compte non vérifié.')
 ids=list(set(registration_ids))
 if not ids or len(ids)>20:raise ValidationError('Une commande doit contenir entre 1 et 20 participants.')
 with transaction.atomic():
  e=Event.objects.select_for_update().get(pk=event.pk)
  now=timezone.now()
  if not e.published or e.starts_at<=now:raise ValidationError('Événement indisponible.')
  if not e.sales_open or e.sales_start and e.sales_start>now or e.sales_end and e.sales_end<=now:raise ValidationError('Les ventes ne sont pas ouvertes.')
  regs=list(Registration.objects.select_related('user').filter(pk__in=ids,event=e))
  if len(regs)!=len(ids) or any(not r.user.verified for r in regs):raise ValidationError('Chaque participant doit avoir validé son compte et sa préinscription.')
  if OrderLine.objects.filter(registration_id__in=ids,held=True).exists():raise ValidationError('Un participant possède déjà un billet ou un paiement en cours.')
  if OrderLine.objects.filter(order__event=e,held=True).count()+len(ids)>e.capacity:raise ValidationError('Il ne reste pas assez de places.')
  order=Order.objects.create(buyer=buyer,event=e,total_cents=e.price_cents*len(regs))
  OrderLine.objects.bulk_create([OrderLine(order=order,registration=r,price_cents=e.price_cents) for r in regs])
  Audit.objects.create(actor=buyer,event=e,action='commande_creee',object_id=str(order.pk))
  return order

def begin_checkout(order):
 if not settings.SUMUP_API_KEY or not settings.SUMUP_MERCHANT_CODE:raise ValidationError('La billetterie ouvrira prochainement.')
 payload={'checkout_reference':str(order.pk),'amount':order.total_cents/100,'currency':'EUR','merchant_code':settings.SUMUP_MERCHANT_CODE,'description':order.event.name,'hosted_checkout':{'enabled':True},'valid_until':(timezone.now()+timedelta(minutes=30)).isoformat(),'redirect_url':settings.SITE_URL+f'/commande/{order.pk}/','return_url':settings.SITE_URL+'/paiement/notification/'}
 try:
  response=requests.post('https://api.sumup.com/v0.1/checkouts',json=payload,headers={'Authorization':'Bearer '+settings.SUMUP_API_KEY},timeout=20)
  response.raise_for_status();data=response.json()
  if not data.get('id') or not data.get('hosted_checkout_url','').startswith('https://checkout.sumup.com/'):
   raise ValueError('unexpected_checkout')
  order.checkout_id=data['id'];order.checkout_url=data['hosted_checkout_url'];order.status='pending';order.save()
 except requests.HTTPError as exc:
  if exc.response is not None and exc.response.status_code in [400,401,403,404,422]:
   with transaction.atomic():
    Order.objects.filter(pk=order.pk).update(status='failed');order.lines.update(held=False)
  else:Order.objects.filter(pk=order.pk).update(status='review')
  raise ValidationError('Paiement indisponible. L’organisation peut vérifier votre commande.')
 except Exception:
  # Never release uncertain payments: a timeout may follow successful checkout creation.
  Order.objects.filter(pk=order.pk).update(status='review')
  raise ValidationError('Paiement temporairement indisponible. Votre commande sera vérifiée par l’organisation.')
 return order.checkout_url

def confirm_payment(order_id,data):
 with transaction.atomic():
  o=Order.objects.select_for_update().select_related('event').get(pk=order_id)
  expected=Decimal(o.total_cents)/100
  if not o.checkout_id or data.get('id')!=o.checkout_id or data.get('checkout_reference')!=str(o.pk) or data.get('currency')!='EUR' or Decimal(str(data.get('amount',-1)))!=expected:
   raise ValidationError('Paiement non conforme à la commande.')
  if settings.SUMUP_MERCHANT_CODE and data.get('merchant_code')!=settings.SUMUP_MERCHANT_CODE:raise ValidationError('Marchand incorrect.')
  if o.status=='paid':return
  status=data.get('status')
  if status=='PAID':
   if o.lines.filter(held=False).exists():
    o.status='review';o.save(update_fields=['status','updated_at'])
    Audit.objects.create(actor=o.buyer,event=o.event,action='paiement_tardif_a_verifier',object_id=str(o.pk));return
   o.status='paid';o.save(update_fields=['status','updated_at'])
   for line in o.lines.select_related('registration__user'):
    t,_=Ticket.objects.get_or_create(line=line)
    Job.objects.get_or_create(key=f'ticket:{t.pk}',defaults={'kind':'ticket','destination':line.registration.user.phone,'payload':{'ticket':str(t.pk)},'next_at':timezone.now()})
   Audit.objects.create(actor=o.buyer,event=o.event,action='paiement_confirme',object_id=str(o.pk))
  elif status=='EXPIRED':
   o.status='failed';o.save(update_fields=['status','updated_at']);o.lines.update(held=False)
  elif status in ['PENDING','FAILED']:
   o.status='pending';o.save(update_fields=['status','updated_at'])

def reconcile_order(order):
 if not settings.SUMUP_API_KEY:return
 headers={'Authorization':'Bearer '+settings.SUMUP_API_KEY}
 if not order.checkout_id:
  r=requests.get('https://api.sumup.com/v0.1/checkouts',params={'checkout_reference':str(order.pk)},headers=headers,timeout=15)
  r.raise_for_status();rows=r.json()
  if not isinstance(rows,list):raise ValidationError('Réponse de réconciliation incorrecte.')
  if len(rows)>1:raise ValidationError('Plusieurs paiements trouvés ; contrôle manuel nécessaire.')
  if not rows:
   # An operator can retry reconciliation once the API has definitively settled the creation.
   if (timezone.now()-order.created_at).total_seconds()>900:
    with transaction.atomic():
     current=Order.objects.select_for_update().get(pk=order.pk)
     if not current.checkout_id and current.status in ['creating','review']:
      current.status='failed';current.save();current.lines.update(held=False)
      Audit.objects.create(actor=order.buyer,event=order.event,action='paiement_absent_apres_delai',object_id=str(order.pk))
   return
  data=rows[0]
  if data.get('checkout_reference')!=str(order.pk):raise ValidationError('Référence incorrecte.')
  order.checkout_id=data['id'];order.checkout_url=data.get('hosted_checkout_url','');order.save(update_fields=['checkout_id','checkout_url','updated_at'])
 r=requests.get('https://api.sumup.com/v0.1/checkouts/'+order.checkout_id,headers=headers,timeout=15)
 r.raise_for_status();confirm_payment(order.pk,r.json())
