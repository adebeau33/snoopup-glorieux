#!/bin/bash
set -euo pipefail
while IFS='=' read -r key value; do export "$key=$value"; done < /etc/glorieux/glorieux.env
cd /opt/snoopup-glorieux
exec sudo -u glorieux --preserve-env=SECRET_KEY,TICKET_SECRET,DEBUG,DATABASE_PATH,ALLOWED_HOSTS,SITE_URL,AWS_REGION,FROM_EMAIL,EMAIL_PROVIDER,AWS_ACCESS_KEY_ID,AWS_SECRET_ACCESS_KEY,SMS_PROVIDER,SUMUP_API_KEY,SUMUP_MERCHANT_CODE,TWILIO_ACCOUNT_SID,TWILIO_AUTH_TOKEN,TWILIO_FROM .venv/bin/python manage.py "$@"
