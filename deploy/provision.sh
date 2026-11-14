#!/bin/bash
set -euo pipefail
id glorieux >/dev/null 2>&1 || useradd --system --home-dir /var/lib/glorieux --shell /sbin/nologin glorieux
install -d -m 755 /opt/snoopup-glorieux
rsync -a --exclude=.venv --exclude=.git --exclude=staticfiles --exclude='*.sqlite3' /home/ec2-user/snoopup-glorieux/ /opt/snoopup-glorieux/
cd /opt/snoopup-glorieux
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.lock --quiet
install -d -m 700 /etc/glorieux
install -d -o glorieux -g glorieux -m 700 /var/lib/glorieux
if [ ! -f /etc/glorieux/glorieux.env ]; then
 python3.12 - <<'PY'
import secrets,os
p='/etc/glorieux/glorieux.env'
values={'SECRET_KEY':secrets.token_urlsafe(64),'TICKET_SECRET':secrets.token_urlsafe(64),'DEBUG':'0','ALLOWED_HOSTS':'glorieux.snoopup.io,localhost,127.0.0.1','SITE_URL':'https://glorieux.snoopup.io','DATABASE_PATH':'/var/lib/glorieux/db.sqlite3','AWS_REGION':'eu-north-1','FROM_EMAIL':'Glorieux <billetterie@snoopup.io>','EMAIL_PROVIDER':'ses','SUMUP_API_KEY':'','SUMUP_MERCHANT_CODE':'','SMS_PROVIDER':''}
with open(p,'x') as f:
 for k,v in values.items():f.write(k+'='+v+'\n')
os.chmod(p,0o600)
PY
fi
set -a
# systemd environment values are unquoted; parse with Python rather than shell source.
while IFS='=' read -r key value; do export "$key=$value"; done < /etc/glorieux/glorieux.env
set +a
sudo -u glorieux --preserve-env=SECRET_KEY,TICKET_SECRET,DEBUG,DATABASE_PATH,ALLOWED_HOSTS,SITE_URL .venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput
python3.12 - <<'PY'
import sqlite3,os
c=sqlite3.connect('/var/lib/glorieux/db.sqlite3');print('Journal SQLite :',c.execute('PRAGMA journal_mode=WAL').fetchone()[0]);c.close()
import pwd
u=pwd.getpwnam('glorieux');os.chown('/var/lib/glorieux/db.sqlite3',u.pw_uid,u.pw_gid)
PY
install -m 644 deploy/glorieux.service /etc/systemd/system/glorieux.service
install -m 644 deploy/glorieux-jobs.service /etc/systemd/system/glorieux-jobs.service
install -m 644 deploy/glorieux-jobs.timer /etc/systemd/system/glorieux-jobs.timer
install -d -m 755 /var/www/glorieux-acme/.well-known/acme-challenge
install -m 644 deploy/glorieux-http.conf /etc/httpd/conf.d/glorieux.snoopup.io.conf
if [ -f /etc/letsencrypt/live/glorieux.snoopup.io/fullchain.pem ]; then
 install -m 644 deploy/glorieux-https.conf /etc/httpd/conf.d/glorieux.snoopup.io-ssl.conf
fi
httpd -t
systemctl daemon-reload
systemctl enable --now glorieux.service glorieux-jobs.timer
systemctl restart glorieux.service glorieux-jobs.timer
systemctl reload httpd
install -m 644 deploy/glorieux-backup.service /etc/systemd/system/glorieux-backup.service
install -m 644 deploy/glorieux-backup.timer /etc/systemd/system/glorieux-backup.timer
systemctl daemon-reload
systemctl enable --now glorieux-backup.timer
