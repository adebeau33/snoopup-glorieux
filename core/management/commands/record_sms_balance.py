from django.core.management.base import BaseCommand
from core.delivery import record_balance
class Command(BaseCommand):
 help='Enregistre un relevé réel de crédits OVH, sans envoi SMS.'
 def add_arguments(self,p):p.add_argument('--credits',required=True)
 def handle(self,*args,**opts):record_balance(opts['credits']);self.stdout.write('Solde OVH horodaté enregistré.')
