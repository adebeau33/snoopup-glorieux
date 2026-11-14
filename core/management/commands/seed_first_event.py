from datetime import datetime
from zoneinfo import ZoneInfo
from django.core.management.base import BaseCommand
from core.models import Event
class Command(BaseCommand):
 help='Crée uniquement la première soirée annoncée, sans ouvrir les ventes.'
 def handle(self,*args,**kwargs):
  event,created=Event.objects.get_or_create(slug='premiere-soiree-21-novembre-2026',defaults={
   'name':'Première soirée Glorieux',
   'description':'Rendez-vous le samedi 21 novembre 2026 à partir de 22 h au Death before sunlight, à Bordeaux. Les places sont limitées : les inscriptions sont traitées par ordre d’arrivée. Aucune inscription ne sera possible sur place le soir de l’événement.',
   'starts_at':datetime(2026,11,21,22,0,tzinfo=ZoneInfo('Europe/Paris')),
   'venue':'Death before sunlight','address':'147 rue des Petits Lapins, 33000 Bordeaux',
   'organizer_name':'BDE Grand Lebrun','organizer_address':'164 avenue Charles de Gaulle, 33200 Bordeaux-Caudéran','capacity':1000,'price_cents':0,'published':True,'sales_open':False})
  Event.objects.filter(pk=event.pk).update(capacity=1000,address='147 rue des Petits Lapins, 33000 Bordeaux',organizer_name='BDE Grand Lebrun',organizer_address='164 avenue Charles de Gaulle, 33200 Bordeaux-Caudéran',description='Rendez-vous le samedi 21 novembre 2026 à partir de 22 h au Death before sunlight, à Bordeaux. Les places sont limitées : les inscriptions sont traitées par ordre d’arrivée. Aucune inscription ne sera possible sur place le soir de l’événement.')
  self.stdout.write('Première soirée créée, jauge 1000, ventes fermées et tarif à renseigner.' if created else 'Première soirée actualisée : jauge 1000 et adresse enregistrées.')
