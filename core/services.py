import hashlib,hmac,secrets
from datetime import timedelta
import phonenumbers
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.contrib.auth.hashers import make_password,check_password
from django.db import transaction
from django.utils import timezone
from .models import Challenge,User,Job,Registration,Audit,RateLimit

DECLARATIONS={
 'adult':'Je déclare être âgé(e) de dix-huit ans révolus à la date de l’événement.',
 'minor':'Je déclare que je serai mineur(e) à la date de l’événement et avoir informé mon ou mes représentants légaux de mon inscription et de ma participation à cette soirée, ainsi que de sa date, de ses horaires et de son lieu.'}

def normalize_phone(value):
 try:
  p=phonenumbers.parse(value,'FR')
  if not phonenumbers.is_valid_number(p):raise ValueError()
  return phonenumbers.format_number(p,phonenumbers.PhoneNumberFormat.E164)
 except Exception:raise ValidationError('Numéro de téléphone invalide.')

def school_email(value):
 if not isinstance(value,str):raise ValidationError('Adresse email obligatoire.')
 value=value.strip().lower();validate_email(value)
 if value.rsplit('@',1)[-1]!='grandlebrun.com' and value not in settings.TEST_ALLOWED_EMAILS:raise ValidationError('Une adresse @grandlebrun.com est obligatoire.')
 return value

def limited(key,maximum=10,seconds=3600):
 # Store only a keyed digest of identifiers, never raw phone numbers or IPs.
 key=hmac.new(settings.SECRET_KEY.encode(),key.encode(),hashlib.sha256).hexdigest()
 with transaction.atomic():
  r,_=RateLimit.objects.select_for_update().get_or_create(key=key,defaults={'reset_at':timezone.now()+timedelta(seconds=seconds)})
  if r.reset_at<=timezone.now():r.count=0;r.reset_at=timezone.now()+timedelta(seconds=seconds)
  r.count+=1;r.save()
  return r.count>maximum

def issue_challenge(user,kind):
 if kind not in ['sms','email']:raise ValidationError('Vérification inconnue.')
 if kind=='sms' and not user.phone:raise ValidationError('Renseignez un numéro de téléphone avant de demander un code SMS.')
 now=timezone.now()
 with transaction.atomic():
  User.objects.select_for_update().get(pk=user.pk)
  recent=Challenge.objects.filter(user=user,kind=kind,created_at__gt=now-timedelta(seconds=60)).exists()
  if recent:raise ValidationError('Patientez 60 secondes avant un nouvel envoi.')
  if limited(f'challenge:{user.pk}:{kind}',5):raise ValidationError('Limite d’envois atteinte. Réessayez plus tard.')
  Challenge.objects.filter(user=user,kind=kind,consumed=False).update(consumed=True)
  code=f'{secrets.randbelow(1000000):06d}' if kind=='sms' else secrets.token_urlsafe(32)
  destination=user.phone if kind=='sms' else school_email(user.email)
  ch=Challenge.objects.create(user=user,kind=kind,digest=make_password(code),destination=destination,expires_at=now+timedelta(minutes=5 if kind=='sms' else 30))
  # Tokens are kept only in a short-lived delivery payload, cleared after sending/expiry.
  Job.objects.create(key=f'challenge:{ch.pk}',kind=kind,destination=destination,payload={'challenge':ch.pk,'code':code},next_at=now)
  return ch,code

def verify_challenge(user,kind,code):
 with transaction.atomic():
  ch=Challenge.objects.select_for_update().filter(user=user,kind=kind,consumed=False).order_by('-created_at').first()
  if not ch or ch.expires_at<=timezone.now() or (kind=='sms' and ch.attempts>=5):return False
  if kind=='sms':ch.attempts+=1
  field='phone' if kind=='sms' else 'email'
  ok=hmac.compare_digest(str(getattr(user,field)),ch.destination) and check_password(code,ch.digest)
  if ok:
   ch.consumed=True
   User.objects.filter(pk=user.pk).update(**{field+'_verified':True})
   Job.objects.filter(key=f'challenge:{ch.pk}').update(payload={})
  ch.save();return ok

def pre_register(user,event,school_class,declaration,code):
 if not user.verified:raise ValidationError('Vérifiez votre email et votre téléphone avant de réserver.')
 if not event.published or event.starts_at<=timezone.now():raise ValidationError('Événement indisponible.')
 if not hmac.compare_digest(code.strip(),event.access_code):raise ValidationError('Code événement incorrect.')
 if declaration not in DECLARATIONS:raise ValidationError('Choisissez votre déclaration de majorité.')
 if not school_class or not school_class.active:raise ValidationError('Choisissez une classe valide.')
 existing=Registration.objects.filter(user=user,event=event).first()
 if existing:return existing
 r=Registration.objects.create(user=user,event=event,school_class=school_class,declaration=declaration,declaration_text=DECLARATIONS[declaration])
 Audit.objects.create(actor=user,event=event,action='preinscription',object_id=str(r.pk));return r

def events_for(user):
 from .models import Event
 if user.is_superuser or user.role=='admin':return Event.objects.all()
 return Event.objects.filter(assignment__user=user).distinct()
