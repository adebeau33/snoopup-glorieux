from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import io
from PIL import Image,ImageDraw,ImageFont
from django.test import override_settings
from django.core.management.base import BaseCommand
from core.models import Event,User,Registration,Order,OrderLine,Ticket
from core.tickets import render_ticket
class Command(BaseCommand):
 help='Crée un aperçu fictif PNG sans enregistrement ni envoi.'
 def add_arguments(self,p):p.add_argument('--output',required=True)
 def handle(self,*args,**opts):
  e=Event(id=999,name='Première soirée Glorieux',starts_at=datetime(2026,11,21,22,tzinfo=ZoneInfo('Europe/Paris')),venue='Death before sunlight',address='147 rue des Petits Lapins, 33000 Bordeaux',is_test=True,organizer_name='BDE Grand Lebrun',organizer_address='164 avenue Charles de Gaulle, 33200 Bordeaux-Caudéran')
  u=User(first_name='Camille',last_name='Martin');r=Registration(user=u,event=e);r.pk=42
  o=Order(event=e,buyer=u,status='test',is_test=True,total_cents=1500)
  line=OrderLine(order=o,registration=r,price_cents=1500)
  t=Ticket(line=line,is_test=True)
  root=Path(opts['output']);root.mkdir(parents=True,exist_ok=True)
  with override_settings(TICKET_SECRET='preview-only-not-a-production-signing-key'):
   image=Image.open(io.BytesIO(render_ticket(t,'png'))).convert('RGB')
  image.save(root/'apercu-billet.png')
  self.stdout.write('Aperçu PNG fictif généré ; aucune donnée en base, aucun envoi.')
