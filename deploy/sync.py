import io,tarfile,subprocess,shlex
from pathlib import Path
root=Path(__file__).resolve().parent.parent
buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w:gz') as tar:
 for p in root.rglob('*'):
  rel=p.relative_to(root)
  if any(x in {'.git','.venv','__pycache__','.secrets','staticfiles','.browser-preview','output'} for x in rel.parts) or p.name.startswith('.env') and p.name!='.env.example' or p.suffix=='.sqlite3':continue
  if p.is_file():tar.add(str(p),arcname=str(rel),recursive=False)
cmd="ssh -o BatchMode=yes -i /root/My_New_server.pem ec2-user@ec2-13-51-188-194.eu-north-1.compute.amazonaws.com 'tar xzf - -C /home/ec2-user/snoopup-glorieux'"
subprocess.run(['ssh','-o','BatchMode=yes','-p','2222','root@10.66.66.1',cmd],input=buf.getvalue(),check=True)
print('Sources synchronisées vers le projet AWS dédié.')
