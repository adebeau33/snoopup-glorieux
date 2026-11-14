import hashlib,hmac,io,re,textwrap
from urllib.parse import urlsplit
from PIL import Image,ImageDraw,ImageFont
import qrcode
from django.conf import settings
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction
from django.utils import timezone
from django.utils.formats import date_format
from .models import Ticket,Device,Assignment,Audit

def ticket_data(ticket):
 return {'r':ticket.line.registration_id,'e':ticket.line.order.event_id,'t':ticket.is_test}

def encoded_ticket_data(data):
 import base64,json
 raw=json.dumps(data,sort_keys=True,separators=(',',':')).encode()
 return base64.urlsafe_b64encode(raw).decode().rstrip('=')

def ticket_token(ticket):
 event_id=int(ticket.line.order.event_id);participant_id=int(ticket.line.registration_id)
 if not 0<event_id<2**24 or not 0<participant_id<2**32:raise ValueError('Event or participant reference exceeds compact QR limits.')
 version='G1T' if ticket.is_test else 'G1R'
 message=version+f'{event_id:06X}{participant_id:08X}'
 key=hmac.new(settings.TICKET_SECRET.encode(),b'glorieux-test-ticket-v1',hashlib.sha256).digest() if ticket.is_test else settings.TICKET_SECRET.encode()
 signature=hmac.new(key,message.encode('ascii'),hashlib.sha256).digest()[:8].hex().upper()
 return version+f'{event_id:06X}'+signature+f'{participant_id:08X}'

def verify_qr_data(value):
 """Verify authenticity before any database lookup. Never disclose the signing key."""
 import base64,json,uuid
 if not isinstance(value,str) or len(value)>2048:raise ValidationError('Format du QR code invalide.',code='format_invalid')
 if value.startswith('https://'):
  url=urlsplit(value)
  if url.netloc!=urlsplit(settings.SITE_URL).netloc or not url.path.startswith('/q/'):raise ValidationError('QR code étranger à cette billetterie.',code='format_invalid')
  value=url.path[3:].strip('/')
 compact=value.upper()
 if re.fullmatch(r'G1[RT][0-9A-F]{30}',compact):
  prefix=compact[:3];event_ref=compact[3:9];signature=compact[9:25];participant_ref=compact[25:33]
  message=prefix+event_ref+participant_ref
  key=hmac.new(settings.TICKET_SECRET.encode(),b'glorieux-test-ticket-v1',hashlib.sha256).digest() if prefix=='G1T' else settings.TICKET_SECRET.encode()
  expected=hmac.new(key,message.encode('ascii'),hashlib.sha256).digest()[:8].hex().upper()
  if not hmac.compare_digest(expected,signature):raise ValidationError('Signature invalide : QR code falsifié ou altéré.',code='signature_invalid')
  return {'r':int(participant_ref,16),'e':int(event_ref,16),'t':prefix=='G1T'}
 try:version,encoded,signature=value.split('.')
 except ValueError:raise ValidationError('QR code incomplet ou illisible.',code='format_invalid')
 if version not in ['v1','t1']:raise ValidationError('Version de billet non reconnue.',code='format_invalid')
 key=hmac.new(settings.TICKET_SECRET.encode(),b'glorieux-test-ticket-v1',hashlib.sha256).digest() if version=='t1' else settings.TICKET_SECRET.encode()
 expected=hmac.new(key,(version+'.'+encoded).encode(),hashlib.sha256).hexdigest()
 if len(signature)!=64 or any(c not in '0123456789abcdef' for c in signature) or not hmac.compare_digest(expected,signature):raise ValidationError('Signature invalide : QR code falsifié ou altéré.',code='signature_invalid')
 try:
  data=json.loads(base64.b64decode(encoded+'='*(-len(encoded)%4),altchars=b'-_',validate=True))
  if set(data)!=set(['r','e','p','c','t']) or type(data['e']) is not int or data['e']<=0 or type(data['p']) is not int or data['p']<0 or data['c']!='EUR' or type(data['t']) is not bool or data['t']!=(version=='t1'):raise ValueError()
  prefix='GL-T-' if data['t'] else 'GL-'
  reference=prefix+str(uuid.UUID(data['r'][len(prefix):])).upper()
  if data['r']!=reference:raise ValueError()
 except Exception:raise ValidationError('Données signées illisibles : contrôle de l’organisation requis.',code='signed_format_invalid')
 data['_legacy']=True
 return data

def resolve_ticket(value):
 data=verify_qr_data(value)
 tickets=Ticket.objects.select_related('line__order__event','line__registration__user')
 try:
  if data.get('_legacy'):
   t=tickets.get(pk=data['r'][5:] if data['t'] else data['r'][3:])
   legacy={'r':('GL-T-' if t.is_test else 'GL-')+str(t.pk).upper(),'e':t.line.order.event_id,'p':t.line.price_cents,'c':'EUR','t':t.is_test}
   if legacy!={key:value for key,value in data.items() if key!='_legacy'}:raise ValidationError('Signature authentique, mais données différentes de la base.',code='authentic_mismatch')
  else:
   qs=tickets.filter(line__registration_id=data['r'],line__order__event_id=data['e'],is_test=data['t']).order_by('-active','-created_at')
   t=qs.first()
   if not t:raise Ticket.DoesNotExist()
 except Ticket.DoesNotExist:raise ValidationError('Signature authentique, mais référence absente de la base. Contrôle de l’organisation requis.',code='authentic_unknown')
 return t

def scan_ticket(user,device,value,event_id=None,mode='entry'):
 if mode not in ['entry','consult']:raise ValidationError('Mode de contrôle inconnu.')
 if not user.is_active or not (user.is_superuser or user.role in ['admin','organizer','validator']):raise PermissionDenied()
 d=Device.objects.filter(pk=device.pk,user=user,approved=True,expires_at__gt=timezone.now()).first()
 if not d:raise PermissionDenied('Téléphone non autorisé ou autorisation expirée.')
 data=verify_qr_data(value)
 if event_id is None:
  assigned=list(Assignment.objects.filter(user=user).values_list('event_id',flat=True))
  if len(assigned)!=1:raise PermissionDenied('Choisissez la soirée à contrôler.')
  event_id=assigned[0]
 if int(event_id)!=data['e']:raise PermissionDenied('Ce billet appartient à une autre soirée.')
 if not (user.is_superuser or user.role=='admin' or Assignment.objects.filter(user=user,event_id=event_id).exists()):raise PermissionDenied('Vous n’êtes pas affecté à cet événement.')
 from .models import Event
 event=Event.objects.filter(pk=event_id).first()
 if not event:raise PermissionDenied('Événement introuvable.')
 if bool(event.is_test)!=data['t']:return {'status':'invalid','message':'Billet TEST non valable en mode réel.' if data['t'] else 'Événement en TEST : les billets réels ne sont pas consommés.'}
 try:t=resolve_ticket(value)
 except ValidationError as exc:
  if exc.code in ['authentic_unknown','authentic_mismatch']:
   from .models import Event
   reference=data['r'] if isinstance(data['r'],str) else ('GL-T-' if data['t'] else 'GL-')+f"{data['r']:08X}"
   Audit.objects.create(actor=user,device=d,event_id=event_id,action=exc.code,object_id=reference)
   return {'status':'unknown','message':exc.messages[0],'reference':reference}
  raise
 with transaction.atomic():
  t=Ticket.objects.select_for_update().get(pk=t.pk)
  if not t.active or t.line.order.status!=('test' if t.is_test else 'paid'):result={'status':'invalid','message':'Billet annulé ou non payé.'}
  elif t.used_at:result={'status':'used','message':'Billet déjà utilisé à '+timezone.localtime(t.used_at).strftime('%H:%M:%S')}
  elif mode=='consult':result={'status':'valid','message':'Billet valide — consultation, aucune entrée enregistrée.'}
  else:
   entry_at=timezone.now()
   changed=Ticket.objects.filter(pk=t.pk,active=True,used_at__isnull=True,line__order__status='test' if t.is_test else 'paid').update(used_at=entry_at,used_by=user)
   if changed:t.used_at=entry_at
   result={'status':'accepted' if changed else 'used','message':'Entrée validée' if changed else 'Billet déjà utilisé'}
  Audit.objects.create(actor=user,device=d,event_id=event_id,action=('consult_' if mode=='consult' else 'scan_')+result['status'],object_id=str(t.pk))
 participant=t.line.registration.user
 result.update(participant=participant.get_full_name(),first_name=participant.first_name,last_name=participant.last_name,reference=t.reference,mode=mode,is_test=t.is_test,entry_at=t.used_at.isoformat() if t.used_at else None)
 if result['status'] in ['accepted','valid']:result['message']='Billet valide, bienvenue '+participant.first_name+' !'
 return result

ADMISSION='Merci de présenter une pièce d’identité à l’entrée afin de permettre la vérification de votre identité. Cette soirée privée est réservée aux membres de l’établissement Sainte-Marie Grand Lebrun munis d’un billet nominatif valide. Toute personne sans billet valide ou extérieure à l’établissement se verra refuser l’accès.'
MENTIONS=[ADMISSION,'Billet personnel — une seule entrée. Ne partagez pas ce QR code.','Ne pas déposer sur la voie publique.','L’abus d’alcool est dangereux pour la santé. À consommer avec modération.','Prévoyez votre retour : désignez un SAM qui ne boit pas.','Billet émis via Snoopup.io, prestataire technique de billetterie.','Snoopup.io n’intervient pas dans l’organisation ni dans le déroulement de la soirée.','Cette mention ne limite pas les responsabilités légalement applicables à chacun.']

import threading
_RENDER_LOCK=threading.Lock()

def render_ticket(ticket,fmt):
 # Serializing image composition keeps memory bounded on the shared 2GB host.
 with _RENDER_LOCK:return _render_ticket(ticket,fmt)

def _render_ticket(ticket,fmt):
 e=ticket.line.order.event;u=ticket.line.registration.user
 navy='#152440';gold='#cfad60';cream='#f6f1e6';muted='#667085'
 def font(size,heading=False):
  path=settings.BASE_DIR/('static/core/font-3.ttf' if heading else 'static/core/font-4.ttf')
  try:return ImageFont.truetype(str(path),size)
  except OSError:return ImageFont.load_default(size=size)
 def centered(draw,text,y,f,color):
  bounds=draw.textbbox((0,0),text,font=f)
  draw.text(((1000-(bounds[2]-bounds[0]))/2,y),text,font=f,fill=color)
 # Compact ticket PNG: attendee, event date and a large, signed QR with the event crest.
 image=Image.new('RGB',(1000,1200),'white');d=ImageDraw.Draw(image)
 if ticket.is_test:
  d.rounded_rectangle((50,24,950,76),radius=8,fill='#c83d4b')
  centered(d,'BILLET TEST — NON VALABLE EN MODE RÉEL',32,font(25,True),'white')
 centered(d,e.name.upper(),100 if ticket.is_test else 44,font(40,True),navy)
 centered(d,u.get_full_name(),165 if ticket.is_test else 115,font(58,True),navy)
 date=date_format(timezone.localtime(e.starts_at),'l d F Y · H:i').upper()
 centered(d,date,238 if ticket.is_test else 190,font(29,True),muted)
 qr=qrcode.QRCode(box_size=24,border=4,error_correction=qrcode.constants.ERROR_CORRECT_H)
 qr.add_data(ticket_token(ticket));qr.make(fit=True)
 qr_image=qr.make_image(fill_color=navy,back_color='white').convert('RGB')
 # A centered badge covers only data modules, not finder patterns; H correction restores them.
 logo=Image.open(settings.BASE_DIR/'static/core/event-logo-source.png').convert('RGBA')
 logo.thumbnail((185,185),Image.Resampling.LANCZOS)
 tile=Image.new('RGBA',(225,225),(255,255,255,255));tile.alpha_composite(logo,((225-logo.width)//2,(225-logo.height)//2))
 ImageDraw.Draw(tile).ellipse((2,2,222,222),outline=(207,173,96,255),width=4)
 qr_image.paste(tile.convert('RGB'),((qr_image.width-225)//2,(qr_image.height-225)//2))
 qr_x=(1000-qr_image.width)//2;qr_y=292 if ticket.is_test else 245
 image.paste(qr_image,(qr_x,qr_y))
 if fmt=='png':
  out=io.BytesIO();image.save(out,format='PNG',optimize=True);return out.getvalue()
 raise ValueError('Unsupported ticket format.')

def render_social(event=None):
 image=Image.new('RGB',(1200,630),'#152440');draw=ImageDraw.Draw(image)
 def f(size):
  for path in ['/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
   try:return ImageFont.truetype(path,size)
   except OSError:pass
  return ImageFont.load_default(size=size)
 draw.rectangle((0,600,1200,630),fill='#cfad60')
 draw.text((65,55),'GLORIEUX · BDE 2026 / 2027',font=f(28),fill='#cfad60')
 title=event.name if event else 'FAIS PARTIE DE L’HISTOIRE.'
 y=155
 for line in textwrap.wrap(title.upper(),23)[:4]:draw.text((60,y),line,font=f(50),fill='#f6f1e6');y+=67
 if event:
  draw.text((65,490),timezone.localtime(event.starts_at).strftime('%d/%m/%Y · %H:%M'),font=f(26),fill='#cfad60')
  draw.text((65,530),event.venue[:45],font=f(24),fill='#f6f1e6')
  draw.text((65,565),'Places limitées · par ordre d’arrivée · aucune inscription sur place',font=f(18),fill='#f6f1e6')
 else:draw.text((65,520),'glorieux.snoopup.io',font=f(27),fill='#cfad60')
 try:
  if event:
   badge=Image.open(settings.BASE_DIR/'static/core/event-logo-source.png').convert('RGBA').resize((350,350),Image.Resampling.LANCZOS)
   image.paste(badge,(795,150),badge)
  else:
   source=Image.open(settings.BASE_DIR/'static/core/logo-source.png').convert('RGBA');sx=source.width/942;sy=source.height/2048
   badge=source.crop((int(160*sx),int(576*sy),int(782*sx),int(1198*sy))).resize((350,350))
   mask=Image.new('L',(350,350));ImageDraw.Draw(mask).ellipse((0,0,349,349),fill=255);image.paste(badge,(795,150),mask)
 except OSError:pass
 out=io.BytesIO();image.save(out,format='PNG');return out.getvalue()


def ticket_attachments(ticket):
 """Attach only the compact PNG billet requested for this event."""
 prefix='glorieux-test' if ticket.is_test else 'glorieux'
 return [(prefix+'.png',render_ticket(ticket,'png'),'image/png')]
