"""Create a project SMS user; never transfer the broad OVH account keys to the app."""
import json,secrets,string,subprocess,shlex,ovh
c=ovh.Client(endpoint='ovh-eu');service='sms-da7562-1';login='glorieux'
try:
 c.get('/sms/'+service+'/users/'+login)
 raise SystemExit('Utilisateur SMS glorieux déjà présent : aucun mot de passe modifié. Vérifier la configuration privée serveur.')
except ovh.exceptions.ResourceNotFoundError:pass
password=''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(8))
c.post('/sms/'+service+'/users',login=login,password=password)
c.put('/sms/'+service+'/users/'+login,ipRestrictions=['13.51.188.194'])
info=c.get('/sms/'+service+'/users/'+login)
values={'SMS_PROVIDER':'ovh','OVH_SMS_ACCOUNT':service,'OVH_SMS_LOGIN':info['login'],'OVH_SMS_PASSWORD':password,'OVH_SMS_SENDER':'DIGITALEVEN','OVH_SMS_USE_SHORT_NUMBER':'0','PAYMENTS_ENABLED':'0'}
script="import sys,json,pathlib,os; p=pathlib.Path('/etc/glorieux/glorieux.env'); d=json.load(sys.stdin); old=dict(line.split('=',1) for line in p.read_text().splitlines() if '=' in line); old.update(d); p.write_text(''.join(k+'='+v+'\\n' for k,v in old.items())); os.chmod(p,0o600); print('Accès SMS dédié installé ; clés OVH globales non transférées.')"
inner='sudo python3.12 -c '+shlex.quote(script)
cmd='ssh -o BatchMode=yes -i /root/My_New_server.pem ec2-user@ec2-13-51-188-194.eu-north-1.compute.amazonaws.com '+shlex.quote(inner)
subprocess.run(['ssh','-o','BatchMode=yes','-p','2222','root@10.66.66.1',cmd],input=json.dumps(values).encode(),check=True)
print('Utilisateur SMS glorieux créé, limité à l’IP AWS. Aucun SMS envoyé.')
