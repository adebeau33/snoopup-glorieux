import os,secrets
from pathlib import Path
from django.core.management.base import BaseCommand
from core.models import User
class Command(BaseCommand):
 help='Crée le superadmin initial, sans afficher son mot de passe.'
 def add_arguments(self,p):p.add_argument('--email',required=True)
 def handle(self,*args,**opts):
  email=opts['email'].strip().lower()
  if User.objects.filter(username=email).exists():self.stdout.write('Compte déjà présent ; aucun mot de passe modifié.');return
  password=secrets.token_urlsafe(24)
  User.objects.create_superuser(username=email,email=email,password=password,first_name='Alban',role='admin',email_verified=True)
  p=Path('/var/lib/glorieux/superadmin-initial.txt')
  fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'w') as f:f.write('URL : https://glorieux.snoopup.io/connexion/\nIdentifiant : '+email+'\nMot de passe initial : '+password+'\nÀ changer après la première connexion.\n')
  self.stdout.write('Superadmin créé ; accès initial enregistré dans le fichier privé serveur.')
