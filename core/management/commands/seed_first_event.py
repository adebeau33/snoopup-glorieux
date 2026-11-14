from datetime import datetime
from zoneinfo import ZoneInfo
import secrets
from django.core.management.base import BaseCommand
from core.models import Event
class Command(BaseCommand):
 help='Crée uniquement la première soirée annoncée, sans ouvrir les ventes.'
 def handle(self,*args,**kwargs):
  event,created=Event.objects.get_or_create(slug='premiere-soiree-21-novembre-2026',defaults={
   'name':'Première soirée Glorieux',
   'description':'Rendez-vous le samedi 21 novembre 2026 à partir de 22 h au Death before sunlight, à Bordeaux. Les informations pratiques et l’ouverture de la billetterie seront annoncées ici.',
   'starts_at':datetime(2026,11,21,22,0,tzinfo=ZoneInfo('Europe/Paris')),
   'venue':'Death before sunlight','address':'Bordeaux — adresse précise à confirmer',
   'organizer_name':'BDE Grand Lebrun','organizer_address':'164 avenue Charles de Gaulle, 33200 Bordeaux-Caudéran','capacity':0,'price_cents':0,'published':True,'sales_open':False,'access_code':secrets.token_urlsafe(12)})
  Event.objects.filter(pk=event.pk).update(organizer_name='BDE Grand Lebrun',organizer_address='164 avenue Charles de Gaulle, 33200 Bordeaux-Caudéran')
  self.stdout.write('Première soirée créée, ventes fermées, tarif et jauge à renseigner.' if created else 'Première soirée déjà présente : aucune donnée modifiée.')
