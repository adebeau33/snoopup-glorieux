import os
from pathlib import Path
BASE_DIR=Path(__file__).resolve().parent.parent
SECRET_KEY=os.environ['SECRET_KEY']
DEBUG=os.getenv('DEBUG','0')=='1'
ALLOWED_HOSTS=os.getenv('ALLOWED_HOSTS','glorieux.snoopup.io,localhost,127.0.0.1,testserver').split(',')
INSTALLED_APPS=['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','core']
MIDDLEWARE=['django.middleware.security.SecurityMiddleware','core.middleware.ClientIPMiddleware','whitenoise.middleware.WhiteNoiseMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF='glorieux.urls'
TEMPLATES=[{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION='glorieux.wsgi.application'
DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':os.getenv('DATABASE_PATH',str(BASE_DIR/'db.sqlite3')),'OPTIONS':{'timeout':20,'transaction_mode':'IMMEDIATE'},'TEST':{'NAME':os.getenv('TEST_DATABASE_PATH','/tmp/glorieux-test.sqlite3')}}}

AUTH_USER_MODEL='core.User'
AUTH_PASSWORD_VALIDATORS=[{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator','OPTIONS':{'min_length':8}},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE='fr-fr'
TIME_ZONE='Europe/Paris'
USE_I18N=True
USE_TZ=True
STATIC_URL='/static/'
STATIC_ROOT=BASE_DIR/'staticfiles'
STATICFILES_DIRS=[BASE_DIR/'static']
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
LOGIN_URL='/connexion/'
LOGIN_REDIRECT_URL='/mon-espace/'
LOGOUT_REDIRECT_URL='/'
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SECURE=not DEBUG
CSRF_COOKIE_SECURE=not DEBUG
SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')
SECURE_SSL_REDIRECT=not DEBUG
SECURE_HSTS_SECONDS=31536000 if not DEBUG else 0
SECURE_CONTENT_TYPE_NOSNIFF=True
SECURE_REFERRER_POLICY='same-origin'
X_FRAME_OPTIONS='DENY'
SESSION_COOKIE_AGE=43200
SITE_URL=os.getenv('SITE_URL','https://glorieux.snoopup.io')
AWS_REGION=os.getenv('AWS_REGION','eu-north-1')
FROM_EMAIL=os.getenv('FROM_EMAIL','Glorieux <billetterie@snoopup.io>')
EMAIL_PROVIDER=os.getenv('EMAIL_PROVIDER','ses')
SMS_PROVIDER=os.getenv('SMS_PROVIDER','')
TWILIO_ACCOUNT_SID=os.getenv('TWILIO_ACCOUNT_SID','')
TWILIO_AUTH_TOKEN=os.getenv('TWILIO_AUTH_TOKEN','')
TWILIO_FROM=os.getenv('TWILIO_FROM','')
SUMUP_API_KEY=os.getenv('SUMUP_API_KEY','')
SUMUP_MERCHANT_CODE=os.getenv('SUMUP_MERCHANT_CODE','')
TICKET_SECRET=os.getenv('TICKET_SECRET',SECRET_KEY)
EMAIL_BACKEND='core.email_backend.SESBackend'
DEFAULT_FROM_EMAIL=FROM_EMAIL
PASSWORD_RESET_TIMEOUT=1800

TEST_ALLOWED_EMAILS={x.strip().lower() for x in os.getenv('TEST_ALLOWED_EMAILS','alban.debeaupuis@gmail.com,alban@audiopro.fr').split(',') if x.strip()}

OVH_SMS_ACCOUNT=os.getenv('OVH_SMS_ACCOUNT','')
OVH_SMS_LOGIN=os.getenv('OVH_SMS_LOGIN','')
OVH_SMS_PASSWORD=os.getenv('OVH_SMS_PASSWORD','')
OVH_SMS_SENDER=os.getenv('OVH_SMS_SENDER','SNOOPUPIO')
PAYMENTS_ENABLED=os.getenv('PAYMENTS_ENABLED','0')=='1'

OVH_SMS_USE_SHORT_NUMBER=os.getenv('OVH_SMS_USE_SHORT_NUMBER','0')=='1'
