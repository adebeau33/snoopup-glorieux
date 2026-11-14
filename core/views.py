import json
from datetime import timedelta
from urllib.parse import urlencode
from django.conf import settings
from django.core import signing
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction
from django.db.models import Count,Sum,Q,Max
from django.http import JsonResponse,HttpResponse,Http404
from django.shortcuts import render,redirect,get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from .models import User,Event,Registration,Order,Ticket,Device,Audit,Job,OrderLine,SmsBalance
from .forms import RegisterForm,EventRegistrationForm,DeviceForm,BuyForm
from .services import issue_challenge,verify_challenge,pre_register,limited,events_for
from .delivery import ticket_sms_ready
from .payments import create_order,create_test_checkout_order,begin_checkout,reconcile_order
from .tickets import resolve_ticket,scan_ticket,render_ticket,verify_qr_data,manually_validate_ticket

def error_message(request,exc):messages.error(request,' '.join(exc.messages) if isinstance(exc,ValidationError) else 'Une erreur temporaire est survenue. Réessayez plus tard.')
def home(request):return render(request,'core/home.html',{'events':Event.objects.filter(published=True,starts_at__gt=timezone.now())})
def event_detail(request,slug):
 e=get_object_or_404(Event,slug=slug,published=True)
 return render(request,'core/event.html',{'event':e})

def register(request):
 if request.user.is_authenticated:return redirect('account')
 form=RegisterForm(request.POST or None)
 if request.method=='POST':
  if limited('register-ip:'+request.META.get('REMOTE_ADDR',''),10):messages.error(request,'Trop de tentatives. Réessayez plus tard.')
  elif form.is_valid():
   try:
    with transaction.atomic():
     u=form.save();issue_challenge(u,'email')
   except ValidationError as exc:error_message(request,exc)
   else:
    login(request,u);return redirect('verify')
 return render(request,'core/form.html',{'form':form,'title':'Rejoins Le Glorieux','eyebrow':'01 / TON COMPTE','submit':'Créer mon compte','intro':'Confirme ton adresse mail pour t’inscrire. Ton téléphone sera confirmé au moment de l’achat.'})

@login_required
@never_cache
def verify(request):
 if request.method=='POST':
  if request.POST.get('action')=='email':
   try:issue_challenge(request.user,'email');messages.success(request,'Demande d’envoi enregistrée.')
   except ValidationError as exc:error_message(request,exc)
 return render(request,'core/verify.html')

@never_cache
def verify_email(request,user_id,token):
 if limited('email-verify-ip:'+request.META.get('REMOTE_ADDR',''),60,60):return HttpResponse('Trop de tentatives.',status=429)
 u=get_object_or_404(User,pk=user_id)
 if verify_challenge(u,'email',token):messages.success(request,'Adresse scolaire vérifiée. Connectez-vous pour poursuivre.')
 else:messages.error(request,'Lien invalide ou expiré. Demandez un nouvel email depuis votre compte.')
 return redirect('verify' if request.user.is_authenticated else 'login')

@login_required
@never_cache
def account(request):
 return render(request,'core/account.html',{'registrations':Registration.objects.filter(user=request.user).select_related('event'),'tickets':Ticket.objects.filter(line__registration__user=request.user,active=True).select_related('line__order__event'),'orders':Order.objects.filter(buyer=request.user).select_related('event')[:20]})

@login_required
def preregister(request,slug):
 e=get_object_or_404(Event,slug=slug,published=True)
 if not request.user.email_verified:return redirect('verify')
 if Registration.objects.filter(user=request.user,event=e).exclude(declaration_version='test').exists():return redirect('buy',slug=slug)
 form=EventRegistrationForm(request.POST or None)
 if request.method=='POST':
  if limited('event-registration:'+str(request.user.pk),20):messages.error(request,'Trop de tentatives. Réessayez plus tard.')
  elif form.is_valid():
   try:
    pre_register(request.user,e,form.cleaned_data['declaration']);return redirect('buy',slug=slug)
   except ValidationError as exc:error_message(request,exc)
 return render(request,'core/form.html',{'form':form,'title':'Ton inscription','eyebrow':'03 / '+e.name,'submit':'M’inscrire à la soirée','intro':'Cette déclaration est personnelle. L’inscription ne réserve pas de place ; seul le paiement confirmé donne droit à un billet.'})

@login_required
@never_cache
def buy(request,slug):
 e=get_object_or_404(Event,slug=slug,published=True)
 if not request.user.email_verified:return redirect('verify')
 mine=Registration.objects.filter(user=request.user,event=e).first()
 if not mine or (not e.is_test and mine.declaration_version=='test'):return redirect('event_registration',slug=slug)
 ready=bool(e.is_test or (settings.PAYMENTS_ENABLED and settings.SUMUP_API_KEY and settings.SUMUP_MERCHANT_CODE and ticket_sms_ready() and e.sales_open))
 form=BuyForm(request.POST or None)
 quote=None;phone_verification=None
 def make_quote(regs):
  ids=sorted(r.pk for r in regs)
  return {'registrations':regs,'total':f'{len(regs)*e.price_cents/100:.2f}','token':signing.dumps({'u':request.user.pk,'e':e.pk,'r':ids,'p':e.price_cents},salt='quote')}
 if request.method=='POST' and request.POST.get('action') in ['verify_phones','resend_phones']:
  try:
   state=signing.loads(request.POST.get('phone_state',''),salt='phone-purchase',max_age=1800)
   if not isinstance(state,dict) or state!={'u':request.user.pk,'e':e.pk,'p':e.price_cents,'r':state.get('r')} or not isinstance(state.get('r'),list):raise signing.BadSignature('invalid purchase state')
   regs=list(Registration.objects.select_related('user').filter(event=e,pk__in=state['r']).order_by('pk'))
   if sorted(r.pk for r in regs)!=sorted(state['r']) or any(not r.user.email_verified for r in regs):raise signing.BadSignature('participants changed')
   if request.POST.get('action')=='resend_phones':
    for r in regs:
     r.user.refresh_from_db()
     if not r.user.phone_verified:
      try:issue_challenge(r.user,'sms')
      except ValidationError as exc:error_message(request,exc)
    phone_verification={'registrations':regs,'token':request.POST.get('phone_state','')}
   else:
    for r in regs:
     r.user.refresh_from_db()
     if not r.user.phone_verified:verify_challenge(r.user,'sms',request.POST.get('phone_code_'+str(r.user_id),'').strip())
   for r in regs:r.user.refresh_from_db()
   if request.POST.get('action')=='verify_phones' and all(r.user.phone_verified for r in regs):quote=make_quote(regs)
   elif request.POST.get('action')=='verify_phones':
    messages.error(request,'Un ou plusieurs codes sont incorrects ou expirés. Vérifie les SMS puis réessaie.')
    phone_verification={'registrations':regs,'token':request.POST.get('phone_state','')}
  except (signing.BadSignature,KeyError,TypeError,ValueError):messages.error(request,'Cette étape a expiré. Relance la vérification de ta commande.')
 elif request.method=='POST' and request.POST.get('confirm')=='yes':
  try:
   quoted=signing.loads(request.POST.get('quote',''),salt='quote',max_age=600)
   ids=quoted.get('r',[]);regs=list(Registration.objects.select_related('user').filter(event=e,pk__in=ids).order_by('pk'))
   expected={'u':request.user.pk,'e':e.pk,'r':sorted(r.pk for r in regs),'p':e.price_cents}
   if quoted!=expected or len(regs)!=len(ids) or not all(r.user.email_verified and r.user.phone_verified for r in regs):raise ValidationError('La commande a changé ou un participant doit recommencer sa vérification par SMS.')
   if not ready:raise ValidationError('La vente de billets n’est pas encore ouverte.')
   order=create_test_checkout_order(request.user,e,[r.pk for r in regs]) if e.is_test else create_order(request.user,e,[r.pk for r in regs])
   return redirect('simulated_sumup_checkout',order_id=order.pk) if e.is_test else redirect(begin_checkout(order))
  except signing.BadSignature:messages.error(request,'Le récapitulatif a expiré. Vérifie à nouveau ta commande.')
  except ValidationError as exc:error_message(request,exc)
 elif request.method=='POST' and form.is_valid():
  if limited('buy:'+str(request.user.pk),20):messages.error(request,'Trop de tentatives. Réessaie plus tard.')
  elif not ready:messages.error(request,'La vente de billets n’est pas encore ouverte.')
  else:
   emails=[x.strip().lower() for x in form.cleaned_data['participants'].splitlines() if x.strip()]
   emails=list(dict.fromkeys([request.user.email,*emails]))
   regs=list(Registration.objects.select_related('user').filter(event=e,user__email__in=emails).order_by('pk'))
   if len(emails)>20 or len(regs)!=len(emails) or any(not r.user.email_verified or r.declaration_version=='test' for r in regs):messages.error(request,'Chaque bénéficiaire doit avoir confirmé son adresse mail et son inscription à cette soirée.')
   else:
    missing=[r for r in regs if not r.user.phone_verified]
    if missing:
     for r in missing:
      try:issue_challenge(r.user,'sms')
      except ValidationError as exc:error_message(request,exc)
     phone_verification={'registrations':regs,'token':signing.dumps({'u':request.user.pk,'e':e.pk,'r':sorted(r.pk for r in regs),'p':e.price_cents},salt='phone-purchase')}
    else:quote=make_quote(regs)
 return render(request,'core/buy.html',{'event':e,'form':form,'ready':ready,'quote':quote,'phone_verification':phone_verification})

@login_required
@never_cache
def simulated_sumup_checkout(request,order_id):
 order=get_object_or_404(Order.objects.select_related('event'),pk=order_id,buyer=request.user,is_test=True,event__is_test=True)
 if request.method=='POST':
  if request.POST.get('action')=='success':
   try:
    with transaction.atomic():
     order=Order.objects.select_for_update().get(pk=order.pk)
     if order.status!='test':
      if order.status!='creating':raise ValidationError('Cette simulation de paiement n’est plus active.')
      lines=list(order.lines.select_related('registration__user'))
      if not lines or any(not line.registration.user.email_verified or not line.registration.user.phone_verified for line in lines):
       raise ValidationError('Un bénéficiaire doit à nouveau confirmer son email et son téléphone. Aucun billet TEST n’a été émis.')
      order.status='test';order.save(update_fields=['status','updated_at'])
      for line in lines:
       ticket=Ticket.objects.create(line=line,is_test=True)
       user=line.registration.user
       Job.objects.bulk_create([Job(key=f'test-checkout-sms:{ticket.pk}',kind='test_ticket_sms',destination=user.phone,payload={'ticket':str(ticket.pk)},next_at=timezone.now()),Job(key=f'test-checkout-email:{ticket.pk}',kind='test_email',destination=user.email,payload={'ticket':str(ticket.pk)},next_at=timezone.now())])
      Audit.objects.create(actor=request.user,event=order.event,action='paiement_sumup_simule_reussi',object_id=str(order.pk))
   except ValidationError as exc:
    error_message(request,exc);return redirect('buy',slug=order.event.slug)
   messages.success(request,'Paiement simulé accepté : aucun montant réel n’a été débité. Les billets TEST sont en cours d’envoi.')
   return redirect('order',order_id=order.pk)
  if request.POST.get('action')=='cancel':
   Order.objects.filter(pk=order.pk,status='creating').update(status='failed',updated_at=timezone.now())
   return redirect('order',order_id=order.pk)
 return render(request,'core/simulated_sumup.html',{'order':order,'lines':order.lines.select_related('registration__user'),'total':f'{order.total_cents/100:.2f}'})

@login_required
@never_cache
def order_detail(request,order_id):
 o=get_object_or_404(Order,pk=order_id,buyer=request.user)
 if request.method=='POST':
  if not limited('reconcile:'+str(request.user.pk),20):
   try:reconcile_order(o);o.refresh_from_db()
   except Exception:messages.error(request,'Vérification temporairement indisponible.')
 return render(request,'core/order.html',{'order':o,'lines':o.lines.select_related('registration__user')})

@csrf_exempt
@require_POST
def payment_notification(request):
 try:
  data=json.loads(request.body[:4096]);checkout_id=data.get('id')
  o=Order.objects.filter(checkout_id=checkout_id).exclude(checkout_id='').first()
  if o and o.status!='paid':
   if limited('callback:'+str(o.pk),10,60):return HttpResponse(status=429)
   reconcile_order(o)
 except Exception:return HttpResponse(status=503)
 return HttpResponse(status=204)

@never_cache
def public_scan(request,value):
 try:data=verify_qr_data(value)
 except ValidationError:raise Http404()
 event=get_object_or_404(Event,pk=data['e'],published=True)
 return redirect('event',slug=event.slug)

@never_cache
def ticket_download(request,token,fmt=None):
 t=get_object_or_404(Ticket.objects.select_related('line__registration__user','line__order__event'),download_token=token,active=True,line__order__status__in=['paid','test'])
 if fmt not in ['png',None]:raise Http404()
 if fmt:
  response=HttpResponse(render_ticket(t,fmt),content_type='image/png')
  response['Content-Disposition']=f'attachment; filename="glorieux-{str(t.pk)[:8]}.{fmt}"'
 else:response=render(request,'core/ticket.html',{'ticket':t,'event':t.line.order.event})
 response['X-Robots-Tag']='noindex, nofollow';response['Referrer-Policy']='no-referrer';return response

@login_required
@never_cache
def validation(request):
 u=request.user
 if not (u.is_superuser or u.role in ['admin','organizer','validator']):raise PermissionDenied()
 d=Device.objects.filter(pk=request.session.get('device_id'),user=u).first() if request.session.get('device_id') else None
 form=DeviceForm(request.POST or None)
 if request.method=='POST' and d and request.POST.get('action')=='authorize_self':
  if not u.is_superuser:raise PermissionDenied()
  d.approved=True;d.expires_at=timezone.now()+timedelta(hours=12);d.save(update_fields=['approved','expires_at'])
  Audit.objects.create(actor=u,device=d,action='autorisation_telephone_superadmin')
  messages.success(request,'Ton téléphone est autorisé pour 12 heures. Tu peux démarrer la caméra.')
  return redirect('validation')
 if request.method=='POST' and d and request.POST.get('action')=='manual_validate':
  event=get_object_or_404(events_for(u),pk=request.POST.get('event'))
  registration=get_object_or_404(Registration.objects.select_related('user'),pk=request.POST.get('registration'),event=event)
  try:
   result=manually_validate_ticket(u,d,registration,event)
   if result['status']=='accepted':messages.success(request,f"Entrée validée à {timezone.localtime(result['entry_at']).strftime('%H:%M:%S')} pour {registration.user.get_full_name()}.")
   elif result['status']=='used':messages.warning(request,f"Déjà présent depuis {timezone.localtime(result['entry_at']).strftime('%H:%M:%S')} : {registration.user.get_full_name()}.")
   else:messages.error(request,'Aucun billet payé et actif ne permet de valider cette entrée.')
  except PermissionDenied as exc:messages.error(request,str(exc))
  query=urlencode({'event':event.pk,'q':request.POST.get('q','')[:100]})
  return redirect(reverse('validation')+'?'+query)
 if request.method=='POST' and not d and form.is_valid():
  if limited('devices:'+str(u.pk),5):messages.error(request,'Trop de demandes d’appareils.')
  else:
   d=Device.objects.create(user=u,name=form.cleaned_data['name'],expires_at=timezone.now()+timedelta(hours=12))
   request.session['device_id']=str(d.pk);return redirect('validation')
 authorized=bool(d and d.approved and d.expires_at>timezone.now())
 validation_events=events_for(u)
 selected_event=None;search_query='';search_results=[]
 if authorized:
  event_id=request.POST.get('event') or request.GET.get('event')
  selected_event=validation_events.filter(pk=event_id).first() if event_id else validation_events.first()
  search_query=(request.POST.get('q') if request.method=='POST' else request.GET.get('q','')).strip()[:100]
  if selected_event and search_query:
   phone_digits=''.join(char for char in search_query if char.isdigit())
   phone_terms={phone_digits} if phone_digits else set()
   if phone_digits.startswith('0'):phone_terms.add('+33'+phone_digits[1:])
   elif phone_digits.startswith('33'):phone_terms.add('+'+phone_digits)
   participant_query=Q(user__first_name__icontains=search_query)|Q(user__last_name__icontains=search_query)|Q(user__email__icontains=search_query)
   for phone_term in phone_terms:participant_query|=Q(user__phone__icontains=phone_term)
   registrations=Registration.objects.filter(event=selected_event).filter(participant_query).select_related('user').order_by('user__last_name','user__first_name')[:30]
   order_status='test' if selected_event.is_test else 'paid'
   for registration in registrations:
    tickets=Ticket.objects.filter(line__registration=registration,line__order__event=selected_event,is_test=selected_event.is_test,active=True,line__order__status=order_status).order_by('-created_at')
    used=tickets.filter(used_at__isnull=False).order_by('-used_at').first()
    ticket=tickets.first()
    if used:status='Présent';entry_at=used.used_at;can_validate=False
    elif ticket:status='Billet valide';entry_at=None;can_validate=True
    else:status='Aucun billet valide';entry_at=None;can_validate=False
    search_results.append({'registration':registration,'status':status,'entry_at':entry_at,'can_validate':can_validate})
 return render(request,'core/validation.html',{'device':d,'form':form,'authorized':authorized,'validation_events':validation_events,'selected_event':selected_event,'search_query':search_query,'search_results':search_results})

@login_required
@require_POST
@never_cache
def scan(request):
 if limited('scan:'+str(request.user.pk),300,60):return JsonResponse({'status':'error','message':'Trop de scans. Patientez.'},status=429)
 try:
  d=Device.objects.get(pk=request.session.get('device_id'),user=request.user)
  data=json.loads(request.body[:4096]);value=str(data.get('value',''))[:2048]
  is_test=value.upper().startswith('GL-T-')
  reference=value[5:] if is_test else (value[3:] if value.upper().startswith('GL-') else value)
  if len(reference)==36:
   from decimal import Decimal,InvalidOperation
   from .tickets import encoded_ticket_data
   signature=str(data.get('signature','')).strip().lower()
   if not signature or not str(data.get('price','')).strip():
    return JsonResponse({'status':'unknown','message':'Le numéro seul ne permet pas de vérifier l’authenticité. Ajoutez le prix et la signature imprimés, ou scannez le QR complet.'})
   try:
    price=Decimal(str(data['price']).replace(',','.'))
    if not price.is_finite() or price<0 or price>100000 or price*100!=(price*100).to_integral_value():raise ValueError()
    payload={'r':('GL-T-' if is_test else 'GL-')+reference.upper(),'e':int(data.get('event',0)),'p':int(price*100),'c':'EUR','t':is_test}
   except (InvalidOperation,ValueError):return JsonResponse({'status':'error','message':'Prix ou référence incorrects.'},status=400)
   value=('t1.' if is_test else 'v1.')+encoded_ticket_data(payload)+'.'+signature
  result=scan_ticket(request.user,d,value,event_id=int(data.get('event',0)),mode=data.get('mode','entry'));return JsonResponse(result)
 except PermissionDenied:return JsonResponse({'status':'error','message':'Accès refusé : téléphone ou événement non autorisé.'},status=403)
 except ValidationError as exc:return JsonResponse({'status':'invalid','message':' '.join(exc.messages)},status=400)
 except (Device.DoesNotExist,ValueError,TypeError) as exc:return JsonResponse({'status':'error','message':'QR code illisible ou téléphone non enregistré.'},status=400)

@login_required
@never_cache
def dashboard(request):
 u=request.user
 if not (u.is_superuser or u.role in ['admin','organizer']):raise PermissionDenied()
 events=events_for(u)
 e=events.filter(pk=request.GET.get('event')).first() if request.GET.get('event','').isdigit() else events.first()
 rows=Registration.objects.none();kpi={}
 if e:
  held=OrderLine.objects.filter(order__event=e,held=True).count()
  paid=Ticket.objects.filter(line__order__event=e,line__order__status='paid',active=True)
  regs=Registration.objects.filter(event=e)
  kpi={'paid':paid.count(),'capacity':e.capacity,'available':max(0,e.capacity-held),'held':held-paid.count(),'entries':paid.filter(used_at__isnull=False).count(),'preregistered':regs.exclude(orderline__held=True,orderline__order__status='paid').distinct().count(),'tests':Ticket.objects.filter(line__order__event=e,is_test=True,active=True).count(),'revenue':f'{(Order.objects.filter(event=e,status="paid").aggregate(n=Sum("total_cents"))["n"] or 0)/100:.2f}'}
  rows=annotated_participants(e)
  q=request.GET.get('q','').strip()[:150]
  if q:rows=rows.filter(Q(user__last_name__icontains=q)|Q(user__first_name__icontains=q))
  if request.GET.get('status')=='paid':rows=rows.filter(paid_count__gt=0)
  elif request.GET.get('status')=='pending':rows=rows.filter(paid_count=0)
 return render(request,'core/dashboard.html',{'events':events,'event':e,'rows':rows.order_by('user__last_name')[:500],'kpi':kpi,'sms_balance':SmsBalance.objects.order_by('-observed_at').first() if u.is_superuser else None})

def privacy(request):return render(request,'core/privacy.html')

def social_image(request,slug=None):
 from .tickets import render_social
 event=get_object_or_404(Event,slug=slug,published=True) if slug else None
 response=HttpResponse(render_social(event),content_type='image/png');response['Cache-Control']='public, max-age=3600';return response

@login_required
@never_cache
def export_participants(request):
 import csv
 if not (request.user.is_superuser or request.user.role in ['admin','organizer']):raise PermissionDenied()
 event=get_object_or_404(events_for(request.user),pk=request.GET.get('event'))
 rows=annotated_participants(event)
 response=HttpResponse(content_type='text/csv; charset=utf-8');response['Content-Disposition']='attachment; filename="participants.csv"';response.write('\ufeff')
 writer=csv.writer(response,delimiter=';');writer.writerow(['Nom','Prénom','Email','Téléphone','Statut','Déclaration','Date/heure d’entrée'])
 def safe(value):
  value=str(value)
  return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
 for r in rows:writer.writerow([safe(x) for x in [r.user.last_name,r.user.first_name,r.user.email,r.user.phone,'Billet payé' if r.paid_count else 'Préinscrit',r.get_declaration_display(),timezone.localtime(r.entry_at).strftime('%d/%m/%Y %H:%M:%S') if r.entry_at else '']])
 Audit.objects.create(actor=request.user,event=event,action='export_participants');return response


def annotated_participants(event):
 return Registration.objects.filter(event=event).select_related('user').annotate(paid_count=Count('orderline__ticket',filter=Q(orderline__ticket__active=True,orderline__order__status='paid',orderline__ticket__is_test=False)),test_count=Count('orderline__ticket',filter=Q(orderline__ticket__active=True,orderline__ticket__is_test=True)),entry_at=Max('orderline__ticket__used_at',filter=Q(orderline__ticket__active=True,orderline__ticket__is_test=event.is_test)))

@login_required
@never_cache
def issue_test_ticket(request,event_id):
 from .forms import TestTicketForm
 from .payments import create_test_order
 if not request.user.is_superuser:raise PermissionDenied()
 event=get_object_or_404(Event,pk=event_id)
 form=TestTicketForm(request.POST or None,initial={'email':request.user.email})
 if request.method=='POST' and form.is_valid():
  try:
   ticket=create_test_order(request.user,event,User.objects.get(email__iexact=form.cleaned_data['email']),form.cleaned_data['send_email'])
   messages.success(request,'Billet TEST créé sans paiement et sans réservation de place réelle.')
   return redirect('ticket',token=ticket.download_token)
  except ValidationError as exc:error_message(request,exc)
 return render(request,'core/form.html',{'form':form,'eyebrow':'SUPERADMIN / MODE TEST','title':'GÉNÉRER UN BILLET TEST','intro':'Active le mode TEST de cet événement dans l’administration. Le QR reste lisible, mais ce billet sera refusé en mode réel. Aucun SMS n’est envoyé par cette opération.','submit':'Générer le PNG de test'})

@login_required
@never_cache
def participants_pdf(request):
 import io
 from xml.sax.saxutils import escape
 from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
 from reportlab.lib import colors
 from reportlab.lib.styles import getSampleStyleSheet
 from reportlab.lib.pagesizes import A4,landscape
 if not (request.user.is_superuser or request.user.role in ['admin','organizer']):raise PermissionDenied()
 event=get_object_or_404(events_for(request.user),pk=request.GET.get('event'))
 list_type=request.GET.get('type','registered')
 if list_type not in ['registered','present']:raise Http404()
 rows=annotated_participants(event).order_by('user__last_name','user__first_name')
 if list_type=='present':rows=rows.filter(entry_at__isnull=False).order_by('entry_at','user__last_name')
 out=io.BytesIO();styles=getSampleStyleSheet();story=[]
 title=('TEST — ' if event.is_test else '')+event.name+(' — présents' if list_type=='present' else ' — inscrits')
 story.append(Paragraph(escape(title),styles['Heading1']));story.append(Paragraph('Généré le '+timezone.localtime().strftime('%d/%m/%Y à %H:%M:%S'),styles['Normal']));story.append(Spacer(1,15))
 data=[['Nom / prénom','Email','Téléphone','Billet']+(['Heure d’entrée'] if list_type=='present' else [])]
 for row in rows:
  values=[row.user.get_full_name(),row.user.email or '',row.user.phone or '',('TEST' if row.test_count else 'Payé') if row.paid_count or row.test_count else 'Inscrit']
  if list_type=='present':values.append(timezone.localtime(row.entry_at).strftime('%d/%m/%Y %H:%M:%S'))
  data.append([Paragraph(escape(str(value)),styles['Normal']) for value in values])
 widths=[180,220,120,100]+([140] if list_type=='present' else [])
 table=Table(data,colWidths=widths,repeatRows=1)
 table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#152440')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('BACKGROUND',(0,1),(-1,-1),colors.HexColor('#f6f1e6')),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#c7c7c7')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]));story.append(table)
 def page_number(c,doc):c.setFont('Helvetica',9);c.drawRightString(800,20,'Glorieux — page '+str(doc.page))
 SimpleDocTemplate(out,pagesize=landscape(A4),rightMargin=40,leftMargin=40,topMargin=35,bottomMargin=35).build(story,onFirstPage=page_number,onLaterPages=page_number)
 Audit.objects.create(actor=request.user,event=event,action='export_pdf_'+list_type)
 response=HttpResponse(out.getvalue(),content_type='application/pdf');response['Content-Disposition']=f'attachment; filename="{list_type}-{event.slug}.pdf"';return response
