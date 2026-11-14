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

def ticket_token(ticket):
 message=f'{ticket.pk}:{ticket.line.order.event_id}:{ticket.line.price_cents}:EUR'
 sig=hmac.new(settings.TICKET_SECRET.encode(),message.encode(),hashlib.sha256).hexdigest()
 return f'{ticket.pk}.{sig}'

def resolve_ticket(value):
 if value.startswith('https://'):
  url=urlsplit(value)
  if url.netloc!=urlsplit(settings.SITE_URL).netloc or not url.path.startswith('/q/'):raise ValidationError('QR code étranger à cette billetterie.')
  value=url.path[3:].strip('/')
 try:t=Ticket.objects.select_related('line__order__event','line__registration__user').get(pk=value.split('.')[0])
 except Exception:raise ValidationError('Billet inconnu.')
 if not hmac.compare_digest(ticket_token(t),value):raise ValidationError('Signature du billet incorrecte.')
 return t

def scan_ticket(user,device,value,event_id=None):
 if not user.is_active or not (user.is_superuser or user.role in ['admin','organizer','validator']):raise PermissionDenied()
 d=Device.objects.filter(pk=device.pk,user=user,approved=True,expires_at__gt=timezone.now()).first()
 if not d:raise PermissionDenied('Téléphone non autorisé ou autorisation expirée.')
 t=resolve_ticket(value);e=t.line.order.event
 if event_id is None:
  assigned=list(Assignment.objects.filter(user=user).values_list('event_id',flat=True))
  if len(assigned)!=1:raise PermissionDenied('Choisissez la soirée à contrôler.')
  event_id=assigned[0]
 if int(event_id)!=e.pk:raise PermissionDenied('Ce billet appartient à une autre soirée.')
 if not (user.is_superuser or user.role=='admin' or Assignment.objects.filter(user=user,event=e).exists()):raise PermissionDenied('Vous n’êtes pas affecté à cet événement.')
 with transaction.atomic():
  t=Ticket.objects.select_for_update().get(pk=t.pk)
  if not t.active or t.line.order.status!='paid':result={'status':'invalid','message':'Billet annulé ou non payé.'}
  elif t.used_at:result={'status':'used','message':'Billet déjà utilisé à '+timezone.localtime(t.used_at).strftime('%H:%M:%S')}
  else:
   changed=Ticket.objects.filter(pk=t.pk,active=True,used_at__isnull=True,line__order__status='paid').update(used_at=timezone.now(),used_by=user)
   result={'status':'accepted' if changed else 'used','message':'Entrée validée' if changed else 'Billet déjà utilisé'}
  Audit.objects.create(actor=user,event=e,action='scan_'+result['status'],object_id=str(t.pk))
 result['participant']=t.line.registration.user.get_full_name();return result

ADMISSION='Merci de présenter une pièce d’identité à l’entrée afin de permettre la vérification de votre identité. Cette soirée privée est réservée aux membres de l’établissement Sainte-Marie Grand Lebrun munis d’un billet nominatif valide. Toute personne sans billet valide ou extérieure à l’établissement se verra refuser l’accès.'
MENTIONS=[ADMISSION,'Billet personnel — une seule entrée. Ne partagez pas ce QR code.','Ne pas déposer sur la voie publique.','L’abus d’alcool est dangereux pour la santé. À consommer avec modération.','Prévoyez votre retour : désignez un SAM qui ne boit pas.','Billet émis via Snoopup.io, prestataire technique de billetterie.','Snoopup.io n’intervient pas dans l’organisation ni dans le déroulement de la soirée.','Cette mention ne limite pas les responsabilités légalement applicables à chacun.']

def render_ticket(ticket,fmt):
 e=ticket.line.order.event;u=ticket.line.registration.user
 fontpath='/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf'
 def font(size):
  for path in [fontpath,'/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
   try:return ImageFont.truetype(path,size)
   except OSError:pass
  return ImageFont.load_default(size=size)
 lines=[];y=230
 for text,size in [(e.name,40),(u.get_full_name(),36),(timezone.localtime(e.starts_at).strftime('%d/%m/%Y · %H:%M'),28),(e.venue,28),(e.address,24),(f'Prix payé : {ticket.line.price_cents/100:.2f} EUR',26)]:
  for line in textwrap.wrap(text,48 if size<30 else 36):
   lines.append((line,size,y));y+=size+12
 qr_y=max(650,y+15);footer_y=qr_y+460
 foot=[]
 for text in [*MENTIONS,'Organisation : '+e.organizer_name,e.organizer_address,'Contact : '+e.organizer_contact]:
  for line in textwrap.wrap(text,82):foot.append((line,footer_y));footer_y+=26
 height=max(1600,footer_y+60)
 img=Image.new('RGB',(1000,height),'#f7efd9');d=ImageDraw.Draw(img)
 d.rectangle((0,0,1000,190),fill='#152440')
 d.text((60,45),'GLORIEUX',font=font(62),fill='#cfad60')
 d.text((60,125),'BDE · VOTRE BILLET',font=font(25),fill='white')
 # Preserve the supplied badge via a circular crop during ticket composition.
 try:
  source=Image.open(settings.BASE_DIR/'static/core/logo-source.png').convert('RGBA')
  sx=source.width/942;sy=source.height/2048
  badge=source.crop((int(160*sx),int(576*sy),int(782*sx),int(1198*sy))).resize((150,150))
  mask=Image.new('L',(150,150));ImageDraw.Draw(mask).ellipse((0,0,149,149),fill=255)
  img.paste(badge,(800,20),mask)
 except OSError:pass
 for line,size,pos in lines:d.text((60,pos),line,font=font(size),fill='#152440')
 qr=qrcode.make(settings.SITE_URL+'/q/'+ticket_token(ticket)+'/').convert('RGB').resize((420,420),Image.Resampling.NEAREST)
 img.paste(qr,(290,qr_y))
 d.text((60,qr_y+435),'Billet '+str(ticket.pk),font=font(18),fill='#152440')
 for line,pos in foot:d.text((60,pos),line,font=font(18),fill='#152440')
 out=io.BytesIO()
 if fmt=='png':img.save(out,format='PNG')
 else:
  from reportlab.lib.pagesizes import A4
  width,page_height=A4;scale=min(width/1000,page_height/height)
  c=canvas.Canvas(out,pagesize=A4);c.drawImage(ImageReader(img),(width-1000*scale)/2,(page_height-height*scale)/2,width=1000*scale,height=height*scale);c.showPage();c.save()
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
 else:draw.text((65,520),'glorieux.snoopup.io',font=f(27),fill='#cfad60')
 try:
  source=Image.open(settings.BASE_DIR/'static/core/logo-source.png').convert('RGBA');sx=source.width/942;sy=source.height/2048
  badge=source.crop((int(160*sx),int(576*sy),int(782*sx),int(1198*sy))).resize((350,350))
  mask=Image.new('L',(350,350));ImageDraw.Draw(mask).ellipse((0,0,349,349),fill=255);image.paste(badge,(795,150),mask)
 except OSError:pass
 out=io.BytesIO();image.save(out,format='PNG');return out.getvalue()
