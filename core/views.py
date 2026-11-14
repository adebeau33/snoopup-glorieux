import json
from datetime import timedelta
from django.conf import settings
from django.core import signing
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError,PermissionDenied
from django.db.models import Count,Sum,Q
from django.http import JsonResponse,HttpResponse,Http404
from django.shortcuts import render,redirect,get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from .models import User,Event,Registration,Order,Ticket,Device,Audit,Job,OrderLine,SchoolClass
from .forms import RegisterForm,PreRegisterForm,DeviceForm,BuyForm
from .services import issue_challenge,verify_challenge,pre_register,limited,events_for
from .delivery import sms_ready
from .payments import create_order,begin_checkout,reconcile_order
from .tickets import resolve_ticket,scan_ticket,render_ticket

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
   u=form.save();login(request,u)
   for kind in ['email','sms']:
    try:issue_challenge(u,kind)
    except ValidationError as exc:error_message(request,exc)
   return redirect('verify')
 return render(request,'core/form.html',{'form':form,'title':'Rejoins les Glorieux','eyebrow':'01 / TON COMPTE','submit':'Créer mon compte','intro':'Ton adresse scolaire et ton téléphone. Deux vérifications pour une soirée bien organisée.'})

@login_required
@never_cache
def verify(request):
 if request.method=='POST':
  action=request.POST.get('action','')
  if action in ['email','sms']:
   try:issue_challenge(request.user,action);messages.success(request,'Demande d’envoi enregistrée.')
   except ValidationError as exc:error_message(request,exc)
  elif action=='code':
   if verify_challenge(request.user,'sms',request.POST.get('code','').strip()):messages.success(request,'Téléphone vérifié.');return redirect('verify')
   messages.error(request,'Code incorrect, expiré ou trop de tentatives.')
 return render(request,'core/verify.html',{'sms_ready':sms_ready()})

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
 return render(request,'core/account.html',{'registrations':Registration.objects.filter(user=request.user).select_related('event','school_class'),'tickets':Ticket.objects.filter(line__registration__user=request.user,active=True).select_related('line__order__event'),'orders':Order.objects.filter(buyer=request.user).select_related('event')[:20]})

@login_required
def preregister(request,slug):
 e=get_object_or_404(Event,slug=slug,published=True)
 if not request.user.verified:return redirect('verify')
 if Registration.objects.filter(user=request.user,event=e).exists():return redirect('buy',slug=slug)
 form=PreRegisterForm(request.POST or None)
 if request.method=='POST':
  if limited('event-code:'+str(request.user.pk),20):messages.error(request,'Trop de tentatives. Réessayez plus tard.')
  elif form.is_valid():
   try:
    pre_register(request.user,e,form.cleaned_data['school_class'],form.cleaned_data['declaration'],form.cleaned_data['code']);return redirect('buy',slug=slug)
   except ValidationError as exc:error_message(request,exc)
 return render(request,'core/form.html',{'form':form,'title':'Ta préinscription','eyebrow':'03 / '+e.name,'submit':'Enregistrer ma préinscription','intro':'Cette déclaration est personnelle. La préinscription ne réserve pas de place ; seul le paiement confirmé donne droit à un billet.'})

@login_required
@never_cache
def buy(request,slug):
 e=get_object_or_404(Event,slug=slug,published=True)
 if not request.user.verified:return redirect('verify')
 mine=Registration.objects.filter(user=request.user,event=e).first()
 if not mine:return redirect('preregister',slug=slug)
 ready=bool(settings.SUMUP_API_KEY and settings.SUMUP_MERCHANT_CODE and sms_ready() and e.sales_open)
 form=BuyForm(request.POST or None)
 quote=None
 if request.method=='POST' and form.is_valid():
  if limited('buy:'+str(request.user.pk),20):messages.error(request,'Trop de tentatives. Réessayez plus tard.')
  elif not ready:messages.error(request,'La vente de billets n’est pas encore ouverte.')
  else:
   emails=[x.strip().lower() for x in form.cleaned_data['participants'].splitlines() if x.strip()]
   emails=list(dict.fromkeys([request.user.email,*emails]))
   regs=list(Registration.objects.select_related('user','school_class').filter(event=e,user__email__in=emails))
   if len(emails)>20 or len(regs)!=len(emails) or any(not r.user.verified for r in regs):messages.error(request,'Chaque bénéficiaire doit avoir validé son compte et sa préinscription pour cette soirée.')
   elif request.POST.get('confirm')!='yes':quote={'registrations':regs,'total':f'{len(regs)*e.price_cents/100:.2f}','token':signing.dumps({'u':request.user.pk,'e':e.pk,'r':sorted(r.pk for r in regs),'p':e.price_cents},salt='quote')}
   else:
    try:
     try:quoted=signing.loads(request.POST.get('quote',''),salt='quote',max_age=600)
     except signing.BadSignature:raise ValidationError('Le récapitulatif a expiré. Vérifiez à nouveau votre commande.')
     if quoted!={'u':request.user.pk,'e':e.pk,'r':sorted(r.pk for r in regs),'p':e.price_cents}:raise ValidationError('La commande ou le prix a changé. Vérifiez à nouveau le récapitulatif.')
     order=create_order(request.user,e,[r.pk for r in regs]);return redirect(begin_checkout(order))
    except ValidationError as exc:error_message(request,exc)
 return render(request,'core/buy.html',{'event':e,'form':form,'ready':ready,'quote':quote})

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
 try:t=resolve_ticket(value)
 except ValidationError:raise Http404()
 return redirect('event',slug=t.line.order.event.slug)

@never_cache
def ticket_download(request,token,fmt=None):
 t=get_object_or_404(Ticket.objects.select_related('line__registration__user','line__order__event'),download_token=token,active=True,line__order__status='paid')
 if fmt not in ['png','pdf',None]:raise Http404()
 if fmt:
  response=HttpResponse(render_ticket(t,fmt),content_type='image/png' if fmt=='png' else 'application/pdf')
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
 if request.method=='POST' and not d and form.is_valid():
  if limited('devices:'+str(u.pk),5):messages.error(request,'Trop de demandes d’appareils.')
  else:
   d=Device.objects.create(user=u,name=form.cleaned_data['name'],expires_at=timezone.now()+timedelta(hours=12))
   request.session['device_id']=str(d.pk);return redirect('validation')
 return render(request,'core/validation.html',{'device':d,'form':form,'authorized':d and d.approved and d.expires_at>timezone.now(),'validation_events':events_for(u)})

@login_required
@require_POST
@never_cache
def scan(request):
 if limited('scan:'+str(request.user.pk),300,60):return JsonResponse({'status':'error','message':'Trop de scans. Patientez.'},status=429)
 try:
  d=Device.objects.get(pk=request.session.get('device_id'),user=request.user)
  data=json.loads(request.body[:4096]);value=str(data.get('value',''))[:2048]
  if len(value)==36:
   from .tickets import ticket_token
   manual=Ticket.objects.filter(pk=value).first()
   if manual:value=ticket_token(manual)
  result=scan_ticket(request.user,d,value,event_id=int(data.get('event',0)));return JsonResponse(result)
 except PermissionDenied:return JsonResponse({'status':'error','message':'Accès refusé : téléphone ou événement non autorisé.'},status=403)
 except (ValidationError,Device.DoesNotExist,ValueError,TypeError) as exc:return JsonResponse({'status':'error','message':'QR code invalide ou téléphone non enregistré.'},status=400)

@login_required
@never_cache
def dashboard(request):
 u=request.user
 if not (u.is_superuser or u.role in ['admin','organizer']):raise PermissionDenied()
 events=events_for(u)
 e=events.filter(pk=request.GET.get('event')).first() if request.GET.get('event','').isdigit() else events.first()
 rows=Registration.objects.none();classes=[];kpi={}
 if e:
  held=OrderLine.objects.filter(order__event=e,held=True).count()
  paid=Ticket.objects.filter(line__order__event=e,line__order__status='paid',active=True)
  regs=Registration.objects.filter(event=e)
  kpi={'paid':paid.count(),'capacity':e.capacity,'available':max(0,e.capacity-held),'held':held-paid.count(),'entries':paid.filter(used_at__isnull=False).count(),'preregistered':regs.exclude(orderline__held=True,orderline__order__status='paid').distinct().count(),'revenue':f'{(Order.objects.filter(event=e,status="paid").aggregate(n=Sum("total_cents"))["n"] or 0)/100:.2f}'}
  classes=SchoolClass.objects.filter(registration__event=e).annotate(total=Count('registration',filter=Q(registration__event=e)),paid=Count('registration',filter=Q(registration__event=e,registration__orderline__ticket__active=True,registration__orderline__order__status='paid'))).distinct()
  rows=regs.select_related('user','school_class').annotate(paid_count=Count('orderline__ticket',filter=Q(orderline__ticket__active=True,orderline__order__status='paid')))
  if request.GET.get('class','').isdigit():rows=rows.filter(school_class_id=request.GET['class'])
  q=request.GET.get('q','').strip()[:150]
  if q:rows=rows.filter(Q(user__last_name__icontains=q)|Q(user__first_name__icontains=q))
  if request.GET.get('status')=='paid':rows=rows.filter(paid_count__gt=0)
  elif request.GET.get('status')=='pending':rows=rows.filter(paid_count=0)
 return render(request,'core/dashboard.html',{'events':events,'event':e,'rows':rows.order_by('user__last_name')[:500],'classes':classes,'kpi':kpi})

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
 rows=Registration.objects.filter(event=event).select_related('user','school_class').annotate(paid_count=Count('orderline__ticket',filter=Q(orderline__ticket__active=True,orderline__order__status='paid')))
 if request.GET.get('class','').isdigit():rows=rows.filter(school_class_id=request.GET['class'])
 response=HttpResponse(content_type='text/csv; charset=utf-8');response['Content-Disposition']='attachment; filename="participants.csv"';response.write('\ufeff')
 writer=csv.writer(response,delimiter=';');writer.writerow(['Nom','Prénom','Email','Téléphone','Classe','Statut','Déclaration'])
 def safe(value):
  value=str(value)
  return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
 for r in rows:writer.writerow([safe(x) for x in [r.user.last_name,r.user.first_name,r.user.email,r.user.phone,r.school_class.name,'Billet payé' if r.paid_count else 'Préinscrit',r.get_declaration_display()]])
 Audit.objects.create(actor=request.user,event=event,action='export_participants');return response
