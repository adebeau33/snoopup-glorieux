import hashlib,hmac,io,textwrap
from urllib.parse import urlsplit
from PIL import Image,ImageDraw,ImageFont
import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from django.conf import settings
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction
from django.utils import timezone
from .models import Ticket,Device,Assignment,Audit

def ticket_data(ticket):
 return {'r':ticket.reference,'e':ticket.line.order.event_id,'p':ticket.line.price_cents,'c':'EUR','t':ticket.is_test}

def encoded_ticket_data(data):
 import base64,json
 raw=json.dumps(data,sort_keys=True,separators=(',',':')).encode()
 return base64.urlsafe_b64encode(raw).decode().rstrip('=')

def ticket_token(ticket):
 encoded=encoded_ticket_data(ticket_data(ticket))
 version='t1' if ticket.is_test else 'v1'
 message=version+'.'+encoded
 key=hmac.new(settings.TICKET_SECRET.encode(),b'glorieux-test-ticket-v1',hashlib.sha256).digest() if ticket.is_test else settings.TICKET_SECRET.encode()
 signature=hmac.new(key,message.encode(),hashlib.sha256).hexdigest()
 return message+'.'+signature

def verify_qr_data(value):
 """Verify authenticity before any database lookup. Never disclose the signing key."""
 import base64,json,uuid
 if not isinstance(value,str) or len(value)>2048:raise ValidationError('Format du QR code invalide.',code='format_invalid')
 if value.startswith('https://'):
  url=urlsplit(value)
  if url.netloc!=urlsplit(settings.SITE_URL).netloc or not url.path.startswith('/q/'):raise ValidationError('QR code étranger à cette billetterie.',code='format_invalid')
  value=url.path[3:].strip('/')
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
 return data

def resolve_ticket(value):
 data=verify_qr_data(value)
 try:t=Ticket.objects.select_related('line__order__event','line__registration__user').get(pk=data['r'][5:] if data['t'] else data['r'][3:])
 except Ticket.DoesNotExist:raise ValidationError('Signature authentique, mais référence absente de la base. Contrôle de l’organisation requis.',code='authentic_unknown')
 if ticket_data(t)!=data:raise ValidationError('Signature authentique, mais données différentes de la base. Contrôle de l’organisation requis.',code='authentic_mismatch')
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
   Audit.objects.create(actor=user,device=d,event_id=event_id,action=exc.code,object_id=data['r'])
   return {'status':'unknown','message':exc.messages[0],'reference':data['r']}
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
 def badge(image,x,y,size):
  try:
   crop=Image.open(settings.BASE_DIR/'static/core/event-logo-source.png').convert('RGBA').resize((size,size),Image.Resampling.LANCZOS)
   image.paste(crop,(x,y),crop)
  except OSError:pass
 # Compose and measure every line before allocating the ticket canvas.
 elements=[];y=385
 def add(text,size=30,heading=False,color=navy,width=60,gap=12):
  nonlocal y
  for line in textwrap.wrap(text,width):elements.append((line,size,heading,color,y));y+=size+gap
 add(e.name.upper(),64,True,width=32)
 y+=20;add('CE SOIR, TU ES DES NÔTRES.',23,True,color='#896c2c')
 add(u.get_full_name(),43,True,width=39);y+=16
 date_y=y;y+=115
 add('LE RENDEZ-VOUS',22,True,color=muted)
 add(e.venue,34,True,width=47)
 add(e.address,25,width=65,gap=10)
 y+=20;tear_y=y;y+=55;test_banner_y=y
 if ticket.is_test:y+=72
 qr_y=y;y+=500
 security_y=y;y+=205
 footer_y=y
 footer=[]
 for text in [*MENTIONS,'Organisation : '+e.organizer_name,e.organizer_address,'Contact : '+e.organizer_contact]:
  if not text or text=='Contact : ':continue
  for line in textwrap.wrap(text,81):footer.append((line,y));y+=27
 height=max(1920,y+95)
 image=Image.new('RGB',(1080,height),navy);d=ImageDraw.Draw(image)
 # Athletics-inspired header and a gold edition strip.
 d.rectangle((0,0,1080,13),fill=gold)
 d.text((65,55),'BDE GRAND LEBRUN / 2026—2027',font=font(25,True),fill=gold)
 d.text((60,90),'GLORIEUX',font=font(112,True),fill=cream)
 d.text((65,220),'TA SOIRÉE. TON PASS. TES SOUVENIRS.',font=font(24,True),fill=gold)
 badge(image,830,58,180)
 # Decorative flash, side accents and perforation marks are drawn as vector shapes.
 for x in [775,800,825]:d.line((x,238,x+16,204),fill=gold,width=3)
 d.rounded_rectangle((35,300,1045,height-38),radius=26,fill=cream)
 d.rounded_rectangle((65,320,370,359),radius=5,fill=gold)
 d.text((80,326),'PASS NOMINATIF / 1 ENTRÉE',font=font(22,True),fill=navy)
 d.text((835,325),'ON SE VOIT LÀ-BAS !',font=font(17,True),fill=navy)
 for text,size,heading,color,pos in elements:d.text((75,pos),text,font=font(size,heading),fill=color)
 for x,label,value in [(75,'LA DATE',timezone.localtime(e.starts_at).strftime('%d.%m.%Y')),(445,'DÈS',timezone.localtime(e.starts_at).strftime('%H h %M')),(735,'TARIF SIMULÉ' if ticket.is_test else 'PRIX PAYÉ',f'{ticket.line.price_cents/100:.2f} €'.replace('.',','))]:
  d.text((x,date_y),label,font=font(19,True),fill=muted)
  d.text((x,date_y+30),value,font=font(43,True),fill=navy)
 for x in range(35,1045,25):d.line((x,tear_y,x+12,tear_y),fill='#adb0b6',width=2)
 d.ellipse((15,tear_y-20,55,tear_y+20),fill=navy);d.ellipse((1025,tear_y-20,1065,tear_y+20),fill=navy)
 if ticket.is_test:
  d.rounded_rectangle((75,test_banner_y-8,1005,test_banner_y+49),radius=6,fill='#cf384c')
  d.text((100,test_banner_y),'BILLET TEST',font=font(38,True),fill='white')
 qr=qrcode.QRCode(box_size=1,border=4,error_correction=qrcode.constants.ERROR_CORRECT_M)
 qr.add_data(settings.SITE_URL+'/q/'+ticket_token(ticket)+'/');qr.make(fit=True)
 qr.box_size=max(1,480//len(qr.get_matrix()))
 qr_image=qr.make_image(fill_color=navy,back_color='white').convert('RGB')
 d.rounded_rectangle((270,qr_y,810,qr_y+490),radius=15,fill='white')
 image.paste(qr_image,((1080-qr_image.width)//2,qr_y+(490-qr_image.height)//2))
 d.text((75,security_y+15),'RÉFÉRENCE UNIQUE',font=font(19,True),fill=muted)
 d.text((75,security_y+45),ticket.reference,font=font(25,True),fill=navy)
 d.text((75,security_y+90),'SIGNATURE HMAC-SHA-256 · AUTHENTICITÉ',font=font(18,True),fill=muted)
 signature=ticket_token(ticket).rsplit('.',1)[-1]
 d.text((75,security_y+120),signature[:32],font=font(22),fill=navy)
 d.text((75,security_y+151),signature[32:],font=font(22),fill=navy)
 d.line((75,footer_y-10,1005,footer_y-10),fill=gold,width=2)
 for line,pos in footer:d.text((75,pos+12),line,font=font(20),fill='#475467')
 d.text((75,height-82),'BILLETTERIE SNOOPUP.IO / LE QR NE DOIT PAS ÊTRE PARTAGÉ',font=font(18,True),fill='#896c2c')
 out=io.BytesIO()
 if fmt=='png':image.save(out,format='PNG')
 else:
  from reportlab.lib.pagesizes import A4
  width,page_height=A4;scale=min(width/1080,page_height/height)
  c=canvas.Canvas(out,pagesize=A4);c.drawImage(ImageReader(image),(width-1080*scale)/2,(page_height-height*scale)/2,width=1080*scale,height=height*scale);c.showPage();c.save()
 return out.getvalue()

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
 """Build both formats from one image composition to bound worker memory."""
 with _RENDER_LOCK:
  png=_render_ticket(ticket,'png')
  from reportlab.lib.pagesizes import A4
  image=Image.open(io.BytesIO(png));width,height=A4;scale=min(width/image.width,height/image.height)
  out=io.BytesIO();pdf=canvas.Canvas(out,pagesize=A4);pdf.drawImage(ImageReader(image),(width-image.width*scale)/2,(height-image.height*scale)/2,width=image.width*scale,height=image.height*scale);pdf.showPage();pdf.save()
  prefix='glorieux-test' if ticket.is_test else 'glorieux'
  return [(prefix+'.png',png,'image/png'),(prefix+'.pdf',out.getvalue(),'application/pdf')]
