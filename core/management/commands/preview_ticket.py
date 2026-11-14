from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import io
from PIL import Image,ImageDraw,ImageFont
from django.test import override_settings
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from django.core.management.base import BaseCommand
from core.models import Event,User,Registration,Order,OrderLine,Ticket
from core.tickets import render_ticket
class Command(BaseCommand):
 help='Crée un aperçu fictif PNG/PDF sans enregistrement ni envoi.'
 def add_arguments(self,p):p.add_argument('--output',required=True)
 def handle(self,*args,**opts):
  e=Event(id=999999,name='Première soirée Glorieux',starts_at=datetime(2026,11,21,22,tzinfo=ZoneInfo('Europe/Paris')),venue='Death before sunlight',address='Bordeaux — adresse précise à confirmer',organizer_name='BDE Grand Lebrun',organizer_address='164 avenue Charles de Gaulle, 33200 Bordeaux-Caudéran')
  u=User(first_name='Camille',last_name='Martin');r=Registration(user=u,event=e)
  o=Order(event=e,buyer=u,status='paid',total_cents=1500)
  line=OrderLine(order=o,registration=r,price_cents=1500)
  t=Ticket(line=line)
  root=Path(opts['output']);root.mkdir(parents=True,exist_ok=True)
  with override_settings(TICKET_SECRET='preview-only-not-a-production-signing-key'):
   image=Image.open(io.BytesIO(render_ticket(t,'png'))).convert('RGB')
  draw=ImageDraw.Draw(image);draw.rectangle((65,267,1015,297),fill='#cfad60');draw.text((75,270),'APERÇU NON VALABLE · TARIF DE 15 EUR PUREMENT ILLUSTRATIF',font=ImageFont.load_default(size=21),fill='#152440')
  image.save(root/'apercu-billet.png')
  width,height=A4;scale=min(width/image.width,height/image.height)
  pdf=canvas.Canvas(str(root/'apercu-billet.pdf'),pagesize=A4);pdf.drawImage(ImageReader(image),(width-image.width*scale)/2,(height-image.height*scale)/2,width=image.width*scale,height=image.height*scale);pdf.showPage();pdf.save()
  self.stdout.write('Aperçus fictifs générés ; aucune donnée en base, aucun envoi. Le prix de 15 EUR est uniquement illustratif.')
