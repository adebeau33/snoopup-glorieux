import requests,boto3
from botocore.config import Config
from django.conf import settings
from django.utils import timezone
from .models import Challenge,Ticket

def sms_ready():
 return settings.SMS_PROVIDER=='twilio' and all([settings.TWILIO_ACCOUNT_SID,settings.TWILIO_AUTH_TOKEN,settings.TWILIO_FROM])

def send_sms(destination,body):
 if not sms_ready():raise RuntimeError('sms_not_configured')
 r=requests.post('https://api.twilio.com/2010-04-01/Accounts/'+settings.TWILIO_ACCOUNT_SID+'/Messages.json',auth=(settings.TWILIO_ACCOUNT_SID,settings.TWILIO_AUTH_TOKEN),data={'To':destination,'From':settings.TWILIO_FROM,'Body':body},timeout=15)
 r.raise_for_status();return r.json()['sid']

def send_email(destination,subject,text):
 if settings.EMAIL_PROVIDER!='ses':raise RuntimeError('email_not_configured')
 r=boto3.client('sesv2',region_name=settings.AWS_REGION,config=Config(connect_timeout=5,read_timeout=10,retries={'max_attempts':1})).send_email(FromEmailAddress=settings.FROM_EMAIL,Destination={'ToAddresses':[destination]},Content={'Simple':{'Subject':{'Data':subject,'Charset':'UTF-8'},'Body':{'Text':{'Data':text,'Charset':'UTF-8'}}}})
 return r['MessageId']

def deliver(job):
 p=job.payload
 if job.kind in ['sms','email']:
  ch=Challenge.objects.filter(pk=p.get('challenge'),consumed=False,expires_at__gt=timezone.now()).first()
  if not ch:return 'expired'
  if job.kind=='sms':return send_sms(job.destination,'Glorieux : votre code de vérification est '+p['code']+'. Valable 5 minutes. Ne le communiquez à personne.')
  url=settings.SITE_URL+f'/verification/email/{ch.user_id}/{p["code"]}/'
  return send_email(job.destination,'Glorieux — vérifiez votre email scolaire','Bienvenue chez Glorieux !\n\nConfirmez votre adresse scolaire avec ce lien valable 30 minutes :\n'+url+'\n\nSi vous n’êtes pas à l’origine de cette demande, ignorez ce message.')
 if job.kind=='reset':
  if (timezone.now()-job.created_at).total_seconds()>1800:return 'expired'
  return send_email(job.destination,p['subject'],p['body'])
 if job.kind=='ticket':
  t=Ticket.objects.select_related('line__order__event').get(pk=p['ticket'])
  if not t.active or t.line.order.status!='paid':return 'cancelled'
  return send_sms(job.destination,'Glorieux — '+t.line.order.event.name+' : votre billet PNG et PDF est disponible ici : '+settings.SITE_URL+'/billet/'+t.download_token+'/')
 raise RuntimeError('unknown_job')
