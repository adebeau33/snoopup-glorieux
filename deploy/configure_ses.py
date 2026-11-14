"""Provision project-only SES credentials; write remotely over stdin, never print secrets."""
import json,shlex,subprocess,boto3
name='snoopup-glorieux-ses'
iam=boto3.client('iam')
account=boto3.client('sts').get_caller_identity()['Account']
policy={'Version':'2012-10-17','Statement':[{'Effect':'Allow','Action':['ses:SendEmail','ses:SendRawEmail'],'Resource':'arn:aws:ses:eu-north-1:'+account+':identity/snoopup.io','Condition':{'StringEquals':{'ses:FromAddress':'billetterie@snoopup.io'}}}]}
try:iam.create_user(UserName=name,Tags=[{'Key':'Project','Value':'snoopup-glorieux'}])
except iam.exceptions.EntityAlreadyExistsException:pass
iam.put_user_policy(UserName=name,PolicyName='SendGlorieuxOnly',PolicyDocument=json.dumps(policy))
keys=iam.list_access_keys(UserName=name)['AccessKeyMetadata']
if keys:raise SystemExit('Une clé SES dédiée existe déjà : arrêt sans remplacement. Vérifier la configuration serveur.')
key=iam.create_access_key(UserName=name)['AccessKey']
values={'AWS_ACCESS_KEY_ID':key['AccessKeyId'],'AWS_SECRET_ACCESS_KEY':key['SecretAccessKey']}
script="import sys,json,pathlib,os; p=pathlib.Path('/etc/glorieux/glorieux.env'); d=json.load(sys.stdin); s=p.read_text(); p.write_text(s+''.join(k+'='+v+'\\n' for k,v in d.items())); os.chmod(p,0o600); print('Identifiants SES dédiés installés dans la configuration privée.')"
inner='sudo python3.12 -c '+shlex.quote(script)
command='ssh -o BatchMode=yes -i /root/My_New_server.pem ec2-user@ec2-13-51-188-194.eu-north-1.compute.amazonaws.com '+shlex.quote(inner)
r=subprocess.run(['ssh','-o','BatchMode=yes','-p','2222','root@10.66.66.1',command],input=json.dumps(values).encode())
if r.returncode:raise SystemExit('Transfert échoué : clé créée, récupération manuelle nécessaire. Aucun secret affiché.')
print('Politique IAM limitée aux emails billetterie@snoopup.io en eu-north-1.')
