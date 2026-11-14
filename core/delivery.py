import requests,boto3
from botocore.config import Config
from django.conf import settings
from django.utils import timezone
from .models import Challenge,Ticket

class ProviderDeliveryUncertain(RuntimeError):pass

def sms_ready():
 if settings.SMS_PROVIDER=='ovh':return all([settings.OVH_SMS_ACCOUNT,settings.OVH_SMS_LOGIN,settings.OVH_SMS_PASSWORD]) and bool(settings.OVH_SMS_SENDER or settings.OVH_SMS_USE_SHORT_NUMBER)
 return settings.SMS_PROVIDER=='twilio' and all([settings.TWILIO_ACCOUNT_SID,settings.TWILIO_AUTH_TOKEN,settings.TWILIO_FROM])

def ticket_sms_ready():
 return sms_ready() and not (settings.SMS_PROVIDER=='ovh' and settings.OVH_SMS_USE_SHORT_NUMBER)

def send_sms(destination,body):
 if not sms_ready():raise RuntimeError('sms_not_configured')
 if not body.isascii() or len(body)>160:raise RuntimeError('sms_must_fit_one_ascii_message')
 if settings.SMS_PROVIDER=='ovh':
  if settings.OVH_SMS_USE_SHORT_NUMBER and ('http://' in body or 'https://' in body):raise RuntimeError('ovh_short_sender_cannot_deliver_links')
  if settings.OVH_SMS_USE_SHORT_NUMBER and not destination.startswith('+33'):raise RuntimeError('ovh_short_sender_france_only')
  try:
   response=requests.post('https://www.ovh.com/cgi-bin/sms/http2sms.cgi',data={'account':settings.OVH_SMS_ACCOUNT,'login':settings.OVH_SMS_LOGIN,'password':settings.OVH_SMS_PASSWORD,'from':'' if settings.OVH_SMS_USE_SHORT_NUMBER else settings.OVH_SMS_SENDER,'senderForResponse':'1' if settings.OVH_SMS_USE_SHORT_NUMBER else '0','to':destination,'message':body,'noStop':'1','SMSencoding':'1','contentType':'application/json','tag':'glorieux'},timeout=(5,15),allow_redirects=False)
  except (requests.Timeout,requests.ConnectionError):raise ProviderDeliveryUncertain('ovh_delivery_unknown')
  if response.status_code!=200:raise RuntimeError('ovh_http_refused')
  try:data=response.json()
  except ValueError:
   lines=response.text.strip().splitlines()
   if len(lines)>=3 and lines[0].strip()=='OK':data={'status':100,'creditLeft':lines[1].strip(),'SmsIds':lines[2].strip().replace(',',' ').split()}
   elif lines and lines[0].strip() in ['KO','KB']:raise RuntimeError('ovh_sms_refused')
   else:raise ProviderDeliveryUncertain('ovh_response_unknown')
  if data.get('status') not in [100,101]:raise RuntimeError('ovh_sms_refused')
  ids=data.get('SmsIds') or data.get('smsIds') or data.get('ids') or []
  if isinstance(ids,str):ids=ids.replace(',',' ').split()
  if not ids:raise ProviderDeliveryUncertain('ovh_missing_receipt')
  if 'creditLeft' in data:
   try:record_balance(data['creditLeft'])
   except Exception:pass
  return ','.join(str(i) for i in ids)
 try:
  r=requests.post('https://api.twilio.com/2010-04-01/Accounts/'+settings.TWILIO_ACCOUNT_SID+'/Messages.json',auth=(settings.TWILIO_ACCOUNT_SID,settings.TWILIO_AUTH_TOKEN),data={'To':destination,'From':settings.TWILIO_FROM,'Body':body},timeout=(5,15))
 except (requests.Timeout,requests.ConnectionError):raise ProviderDeliveryUncertain('twilio_delivery_unknown')
 r.raise_for_status();return r.json()['sid']

def send_email(destination,subject,text,html=None,attachments=None):
 if settings.EMAIL_PROVIDER!='ses':raise RuntimeError('email_not_configured')
 body={'Text':{'Data':text,'Charset':'UTF-8'}}
 if html:body['Html']={'Data':html,'Charset':'UTF-8'}
 content={'Simple':{'Subject':{'Data':subject,'Charset':'UTF-8'},'Body':body}}
 if attachments:
  from email.message import EmailMessage
  from email.policy import SMTP
  message=EmailMessage(policy=SMTP);message['From']=settings.FROM_EMAIL;message['To']=destination;message['Subject']=subject;message.set_content(text)
  if html:message.add_alternative(html,subtype='html')
  for filename,data,mime in attachments:
   maintype,subtype=mime.split('/',1);message.add_attachment(data,maintype=maintype,subtype=subtype,filename=filename)
  content={'Raw':{'Data':message.as_bytes()}}
 r=boto3.client('sesv2',region_name=settings.AWS_REGION,config=Config(connect_timeout=5,read_timeout=10,retries={'total_max_attempts':1})).send_email(FromEmailAddress=settings.FROM_EMAIL,Destination={'ToAddresses':[destination]},Content=content)
 return r['MessageId']

def deliver(job):
 p=job.payload
 if job.kind in ['sms','email']:
  ch=Challenge.objects.filter(pk=p.get('challenge'),consumed=False,expires_at__gt=timezone.now()).first()
  if not ch:return 'expired'
  if job.kind=='sms':return send_sms(job.destination,'Glorieux - Code de verification : '+p['code']+'. Valable 5 min. Ne partagez pas ce code.')
  url=settings.SITE_URL+f'/verification/email/{ch.user_id}/{p["code"]}/'
  from django.template.loader import render_to_string
  html=render_to_string('emails/verify.html',{'url':url,'site_url':settings.SITE_URL})
  return send_email(job.destination,'Glorieux — vérifiez votre email scolaire','Bienvenue chez Glorieux !\n\nConfirmez votre adresse scolaire avec ce lien valable 30 minutes :\n'+url+'\n\nSi vous n’êtes pas à l’origine de cette demande, ignorez ce message.',html=html)
 if job.kind=='reset':
  if (timezone.now()-job.created_at).total_seconds()>1800:return 'expired'
  return send_email(job.destination,p['subject'],p['body'])
 if job.kind in ['test_email','ticket_email']:
  from .tickets import ticket_attachments
  is_test=job.kind=='test_email'
  t=Ticket.objects.select_related('line__order__event').get(pk=p['ticket'],is_test=is_test)
  if not t.active or t.line.order.status!=('test' if is_test else 'paid'):return 'cancelled'
  url=settings.SITE_URL+'/billet/'+t.download_token+'/'
  title='Glorieux — votre billet TEST' if is_test else 'Glorieux — votre billet'
  text=('Billet TEST enregistré pour ' if is_test else 'Votre billet pour ')+t.line.order.event.name+'\n\n'
  if is_test:text+='Aucun paiement effectué. Ce billet permet de tester le contrôle dans l’événement en mode TEST. Il n’est pas valable pour une entrée réelle.\n\n'
  text+='Votre PNG et votre PDF sont joints à cet email. Vous pouvez aussi les retrouver ici : '+url
  return send_email(job.destination,title,text,attachments=ticket_attachments(t))
 if job.kind=='test_ticket_sms':
  t=Ticket.objects.select_related('line__order__event').get(pk=p['ticket'],is_test=True,active=True,line__order__status='test')
  return send_sms(job.destination,'Glorieux - Votre billet TEST PNG/PDF : '+settings.SITE_URL+'/billet/'+t.download_token+'/')
 if job.kind=='ticket':
  t=Ticket.objects.select_related('line__order__event').get(pk=p['ticket'])
  if not t.active or t.line.order.status!='paid':return 'cancelled'
  return send_sms(job.destination,'Glorieux - Votre billet PNG/PDF : '+settings.SITE_URL+'/billet/'+t.download_token+'/')
 raise RuntimeError('unknown_job')

def record_balance(value):
 from decimal import Decimal
 from .models import SmsBalance
 credits=Decimal(str(value))
 if not credits.is_finite() or credits<0:return
 SmsBalance.objects.update_or_create(pk=1,defaults={'credits':credits,'observed_at':timezone.now(),'source':'ovh'})
