from datetime import timedelta
from django.test import TestCase,override_settings
from django.utils import timezone
from django.core.exceptions import ValidationError,PermissionDenied
from .models import User,Event,Registration,Order,OrderLine,Ticket,Device,Assignment,Job,Challenge
from .services import normalize_phone,school_email,issue_challenge,verify_challenge,pre_register
from .payments import create_order,confirm_payment
from .tickets import ticket_token,scan_ticket

class PlatformTests(TestCase):
 def setUp(self):
  self.u=User.objects.create_user(username='eleve@grandlebrun.com',email='eleve@grandlebrun.com',password='UnMotDePasse!672',first_name='Camille',last_name='Martin',phone='+33612345678',email_verified=True,phone_verified=True)
  self.e=Event.objects.create(name='Soirée',slug='soiree',starts_at=timezone.now()+timedelta(days=30),venue='Salle',address='Bordeaux',capacity=2,price_cents=1500,published=True,sales_open=True)
 def reg(self,u=None):
  return pre_register(u or self.u,self.e,'adult')
 def test_email_exact_domain(self):
  self.assertEqual(school_email(' X@GrandLebrun.com '),'x@grandlebrun.com')
  for email in ['x@gmail.com','x@grandlebrun.com.evil.fr','x@sub.grandlebrun.com']:
   with self.assertRaises(ValidationError):school_email(email)
 def test_phone_normalization(self):
  self.assertEqual(normalize_phone('06 12 34 56 78'),'+33612345678')
 def test_registration_requires_email_but_not_phone(self):
  self.u.phone_verified=False;self.u.save()
  self.assertEqual(self.reg().user,self.u)
  self.u.email_verified=False;self.u.save()
  with self.assertRaises(ValidationError):self.reg()
 def test_declaration_is_required(self):
  for choice in ['', 'adult,minor']:
   with self.assertRaises(ValidationError):pre_register(self.u,self.e,choice)
 def test_challenge_single_use_and_limit(self):
  ch,code=issue_challenge(self.u,'sms')
  with self.assertRaises(ValidationError):issue_challenge(self.u,'sms')
  self.assertTrue(verify_challenge(self.u,'sms',code))
  self.assertFalse(verify_challenge(self.u,'sms',code))
 def test_expired_challenge(self):
  ch,code=issue_challenge(self.u,'sms');Challenge.objects.filter(pk=ch.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
  self.assertFalse(verify_challenge(self.u,'sms',code))
 def test_order_and_idempotent_payment(self):
  o=create_order(self.u,self.e,[self.reg().pk]);o.checkout_id='checkout1';o.save()
  payload={'id':'checkout1','status':'PAID','amount':15,'currency':'EUR','checkout_reference':str(o.pk)}
  confirm_payment(o.pk,payload);confirm_payment(o.pk,payload)
  self.assertEqual(Ticket.objects.count(),1)
 def test_payment_mismatch_refused(self):
  o=create_order(self.u,self.e,[self.reg().pk]);o.checkout_id='checkout1';o.save()
  with self.assertRaises(ValidationError):confirm_payment(o.pk,{'id':'checkout1','status':'PAID','amount':1,'currency':'EUR','checkout_reference':str(o.pk)})
  self.assertEqual(Ticket.objects.count(),0)
 def test_pending_holds_capacity(self):
  r=self.reg();o=create_order(self.u,self.e,[r.pk])
  with self.assertRaises(ValidationError):create_order(self.u,self.e,[r.pk])
  self.assertEqual(o.total_cents,1500)
 def test_cannot_buy_for_unverified_participant(self):
  r=self.reg();self.u.phone_verified=False;self.u.save()
  with self.assertRaises(ValidationError):create_order(self.u,self.e,[r.pk])
 def paid_ticket(self):
  o=create_order(self.u,self.e,[self.reg().pk]);o.checkout_id='c';o.save()
  confirm_payment(o.pk,{'id':'c','status':'PAID','amount':15,'currency':'EUR','checkout_reference':str(o.pk)})
  return Ticket.objects.get()
 def test_public_scan_never_consumes(self):
  t=self.paid_ticket()
  response=self.client.get('/q/'+ticket_token(t)+'/')
  self.assertEqual(response.status_code,302);t.refresh_from_db();self.assertIsNone(t.used_at)
 def test_ticket_download_requires_private_token(self):
  t=self.paid_ticket()
  self.assertEqual(self.client.get('/billet/'+str(t.pk)+'/png/').status_code,404)
  for fmt,ctype in [('png','image/png'),('pdf','application/pdf')]:
   response=self.client.get('/billet/'+t.download_token+'/'+fmt+'/')
   self.assertEqual(response.status_code,200);self.assertEqual(response['Content-Type'],ctype)
 def test_device_and_double_scan(self):
  t=self.paid_ticket();v=User.objects.create_user(username='valideur',role='validator')
  Assignment.objects.create(user=v,event=self.e)
  d=Device.objects.create(user=v,approved=True,expires_at=timezone.now()+timedelta(hours=8))
  self.assertEqual(scan_ticket(v,d,ticket_token(t))['status'],'accepted')
  self.assertEqual(scan_ticket(v,d,ticket_token(t))['status'],'used')
  Device.objects.filter(pk=d.pk).update(approved=False)
  with self.assertRaises(PermissionDenied):scan_ticket(v,d,ticket_token(t))
 def test_unknown_event_for_validator(self):
  t=self.paid_ticket();v=User.objects.create_user(username='v2',role='validator')
  d=Device.objects.create(user=v,approved=True,expires_at=timezone.now()+timedelta(hours=8))
  with self.assertRaises(PermissionDenied):scan_ticket(v,d,ticket_token(t))
 def test_tampered_signature(self):
  t=self.paid_ticket();v=User.objects.create_user(username='v3',role='validator');Assignment.objects.create(user=v,event=self.e)
  d=Device.objects.create(user=v,approved=True,expires_at=timezone.now()+timedelta(hours=8))
  with self.assertRaises(ValidationError):scan_ticket(v,d,ticket_token(t)+'x')
 def test_dashboard_requires_staff(self):
  self.client.force_login(self.u)
  self.assertEqual(self.client.get('/gestion/').status_code,403)
 def test_admin_cannot_promote_superadmin(self):
  a=User.objects.create_user(username='admin',role='admin',is_staff=True)
  self.client.force_login(a)
  self.assertEqual(self.client.get('/admin/core/user/').status_code,200)
  root=User.objects.create_superuser(username='root',email='root@example.com',password='Secret!123456')
  self.assertEqual(self.client.get('/admin/core/user/'+str(root.pk)+'/change/').status_code,302)
  self.assertNotContains(self.client.get('/admin/core/user/'),'root@example.com')
 def test_home(self):
  response=self.client.get('/');self.assertContains(response,'GLORIEUX')

class AdditionalSecurityTests(TestCase):
 setUp=PlatformTests.setUp
 reg=PlatformTests.reg
 def test_closed_sales_block_even_in_debug(self):
  self.e.sales_open=False;self.e.save()
  with self.assertRaises(ValidationError):create_order(self.u,self.e,[self.reg().pk])
 def test_no_sumup_no_order(self):
  self.reg();self.client.force_login(self.u)
  response=self.client.post('/evenement/soiree/billets/',{'participants':'','confirm':'yes'})
  self.assertEqual(response.status_code,200);self.assertEqual(Order.objects.count(),0)
 def test_organizer_cannot_view_other_event(self):
  organizer=User.objects.create_user(username='orga',role='organizer',is_staff=True)
  self.client.force_login(organizer)
  response=self.client.get('/gestion/?event='+str(self.e.pk))
  self.assertNotContains(response,'Terminale A')
 def test_verification_attempts_exhausted(self):
  ch,code=issue_challenge(self.u,'sms')
  bad='000001' if code=='000000' else '000000'
  for _ in range(5):self.assertFalse(verify_challenge(self.u,'sms',bad))
  self.assertFalse(verify_challenge(self.u,'sms',code))

from concurrent.futures import ThreadPoolExecutor
from django.test import TransactionTestCase
from django.db import connections
class ConcurrencyTests(TransactionTestCase):
 def test_simultaneous_orders_respect_capacity(self):
  e=Event.objects.create(name='Concurrent',slug='concurrent',starts_at=timezone.now()+timedelta(days=2),venue='Salle',address='Bordeaux',capacity=1,price_cents=1000,published=True,sales_open=True)
  regs=[]
  for i in range(8):
   u=User.objects.create_user(username=f'u{i}',email=f'u{i}@grandlebrun.com',phone=f'+3360000000{i}',email_verified=True,phone_verified=True)
   regs.append(pre_register(u,e,'adult'))
  def buy(r):
   connections.close_all()
   try:create_order(r.user,e,[r.pk]);return 'ok'
   except ValidationError:return 'full'
   finally:connections.close_all()
  with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(buy,regs))
  self.assertEqual(results.count('ok'),1);self.assertEqual(OrderLine.objects.filter(held=True).count(),1)
 def test_simultaneous_scans_accept_once(self):
  e=Event.objects.create(name='Scans',slug='scans',starts_at=timezone.now()+timedelta(days=2),venue='Salle',address='Bordeaux',capacity=1,price_cents=1000,published=True,sales_open=True)
  u=User.objects.create_user(username='s',email='s@grandlebrun.com',phone='+33612345678',email_verified=True,phone_verified=True)
  r=pre_register(u,e,'adult');o=create_order(u,e,[r.pk]);o.checkout_id='c';o.save()
  confirm_payment(o.pk,{'id':'c','checkout_reference':str(o.pk),'status':'PAID','amount':10,'currency':'EUR'})
  t=Ticket.objects.get();v=User.objects.create_user(username='scan',role='validator');Assignment.objects.create(user=v,event=e)
  d=Device.objects.create(user=v,approved=True,expires_at=timezone.now()+timedelta(hours=2));value=ticket_token(t)
  def scan(_):
   connections.close_all()
   try:return scan_ticket(v,d,value)['status']
   finally:connections.close_all()
  with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(scan,range(8)))
  self.assertEqual(results.count('accepted'),1);self.assertEqual(results.count('used'),7)

class ProxyTests(TestCase):
 def test_trusted_proxy_uses_replaced_client_ip(self):
  from django.test import RequestFactory
  from core.middleware import ClientIPMiddleware
  request=RequestFactory().get('/',REMOTE_ADDR='127.0.0.1',HTTP_X_REAL_IP='198.51.100.10')
  ClientIPMiddleware(lambda r:r)(request)
  self.assertEqual(request.META['REMOTE_ADDR'],'198.51.100.10')
 def test_external_cannot_spoof_client_ip(self):
  from django.test import RequestFactory
  from core.middleware import ClientIPMiddleware
  request=RequestFactory().get('/',REMOTE_ADDR='198.51.100.20',HTTP_X_REAL_IP='198.51.100.10')
  ClientIPMiddleware(lambda r:r)(request)
  self.assertEqual(request.META['REMOTE_ADDR'],'198.51.100.20')

class ReviewRegressionTests(TestCase):
 setUp=PlatformTests.setUp
 reg=PlatformTests.reg
 paid_ticket=PlatformTests.paid_ticket
 def test_wrong_selected_event_refused(self):
  t=self.paid_ticket();v=User.objects.create_user(username='multi',role='validator')
  Assignment.objects.create(user=v,event=self.e)
  d=Device.objects.create(user=v,approved=True,expires_at=timezone.now()+timedelta(hours=2))
  with self.assertRaises(PermissionDenied):scan_ticket(v,d,ticket_token(t),event_id=self.e.pk+1)
 def test_password_reset_is_queued(self):
  response=self.client.post('/mot-de-passe/',{'email':self.u.email})
  self.assertEqual(response.status_code,302)
  self.assertTrue(Job.objects.filter(kind='reset').exists())
 def test_email_guess_does_not_burn_real_link(self):
  ch,code=issue_challenge(self.u,'email')
  for _ in range(7):self.assertFalse(verify_challenge(self.u,'email','incorrect'))
  self.assertTrue(verify_challenge(self.u,'email',code))
 def test_failed_attempt_does_not_release_live_checkout(self):
  o=create_order(self.u,self.e,[self.reg().pk]);o.checkout_id='failed';o.save()
  confirm_payment(o.pk,{'id':'failed','status':'FAILED','amount':15,'currency':'EUR','checkout_reference':str(o.pk)})
  self.assertTrue(o.lines.get().held)

class ExportTests(TestCase):
 setUp=PlatformTests.setUp
 reg=PlatformTests.reg
 def test_student_cannot_export(self):
  self.reg();self.client.force_login(self.u)
  self.assertEqual(self.client.get('/gestion/export/?event='+str(self.e.pk)).status_code,403)
 def test_organizer_export_scoped_and_csv_safe(self):
  self.u.first_name='=HYPERLINK("evil")';self.u.save();self.reg()
  org=User.objects.create_user(username='export',role='organizer');self.client.force_login(org)
  self.assertEqual(self.client.get('/gestion/export/?event='+str(self.e.pk)).status_code,404)
  Assignment.objects.create(user=org,event=self.e)
  response=self.client.get('/gestion/export/?event='+str(self.e.pk))
  self.assertEqual(response.status_code,200);self.assertIn("'=HYPERLINK",response.content.decode())

class PresentationTests(TestCase):
 def test_signup_explains_email_confirmation_and_shows_logo(self):
  response=self.client.get('/inscription/')
  self.assertContains(response,'Un email de confirmation vous sera envoyé')
  self.assertContains(response,'nav-logo')
 def test_first_event_datetime_and_sales_closed(self):
  from django.core.management import call_command
  call_command('seed_first_event',verbosity=0)
  event=Event.objects.get(slug='premiere-soiree-21-novembre-2026')
  self.assertEqual(timezone.localtime(event.starts_at).strftime('%Y-%m-%d %H:%M'),'2026-11-21 22:00')
  self.assertFalse(event.sales_open)
  self.assertContains(self.client.get('/evenement/'+event.slug+'/'),'Tarif à venir')

class AdmissionTests(TestCase):
 setUp=PlatformTests.setUp
 def test_event_displays_private_admission(self):
  response=self.client.get('/evenement/soiree/')
  self.assertContains(response,'pièce d’identité')
  self.assertContains(response,'Sainte-Marie Grand Lebrun')
  self.assertContains(response,'Places limitées')
  self.assertContains(response,'Aucune inscription ne sera possible sur place')
  self.assertContains(response,'event-logo-source.png')

class LongTicketTests(TestCase):
 setUp=PlatformTests.setUp
 reg=PlatformTests.reg
 paid_ticket=PlatformTests.paid_ticket
 def test_long_valid_fields_keep_complete_ticket(self):
  import io
  from PIL import Image
  from core.tickets import render_ticket
  self.u.first_name='Alexandre '*15;self.u.last_name='De La Roche '*12;self.u.save()
  self.e.name='Une très longue soirée '*9;self.e.address='Une adresse complète et détaillée '*15;self.e.save()
  ticket=self.paid_ticket()
  image=Image.open(io.BytesIO(render_ticket(ticket,'png')))
  self.assertGreater(image.height,1800)
  self.assertEqual(image.width,1080)

class AdminRequestTests(TestCase):
 def test_exact_test_addresses_only(self):
  for email in ['alban.debeaupuis@gmail.com','alban@audiopro.fr']:self.assertEqual(school_email(email),email)
  for email in ['autre@gmail.com','autre@audiopro.fr','alban@audiopro.fr.evil.com']:
   with self.assertRaises(ValidationError):school_email(email)
 def test_signup_has_no_admin_option_or_rights(self):
  from core.forms import RegisterForm
  form=RegisterForm({'first_name':'Alban','last_name':'Test','email':'alban@audiopro.fr','phone':'0612345678','password1':'Secret!Test2026abcdef','password2':'Secret!Test2026abcdef'})
  self.assertTrue(form.is_valid(),form.errors)
  self.assertNotIn('admin_requested',form.fields)
  u=form.save();self.assertEqual(u.role,'student');self.assertFalse(u.is_staff)
 def test_superadmin_can_approve_request(self):
  from django.contrib import admin
  from django.test import RequestFactory
  from core.admin import Users
  u=User.objects.create_user(username='pending')
  root=User.objects.create_superuser(username='super',email='super@example.com',password='Test!20261234')
  request=RequestFactory().post('/admin/');request.user=root
  Users(User,admin.site).approve_admins(request,User.objects.filter(pk=u.pk))
  u.refresh_from_db();self.assertEqual(u.role,'admin');self.assertTrue(u.is_staff)
 def test_admin_cannot_approve_request(self):
  from django.contrib import admin
  from django.test import RequestFactory
  from core.admin import Users
  u=User.objects.create_user(username='pending')
  a=User.objects.create_user(username='ordinary',role='admin',is_staff=True)
  request=RequestFactory().post('/admin/');request.user=a
  with self.assertRaises(PermissionDenied):Users(User,admin.site).approve_admins(request,User.objects.filter(pk=u.pk))

class AuthenticityTests(TestCase):
 setUp=PlatformTests.setUp
 reg=PlatformTests.reg
 paid_ticket=PlatformTests.paid_ticket
 def test_signature_can_be_checked_without_database(self):
  from core.tickets import verify_qr_data
  ticket=self.paid_ticket();value=ticket_token(ticket);reference=ticket.reference;ticket.delete()
  with self.assertNumQueries(0):data=verify_qr_data(value)
  self.assertEqual(data['r'],reference)
 def test_authentic_unknown_ticket_is_distinct(self):
  ticket=self.paid_ticket();value=ticket_token(ticket);ticket.delete()
  v=User.objects.create_user(username='unknown-validator',role='validator');Assignment.objects.create(user=v,event=self.e)
  d=Device.objects.create(user=v,approved=True,expires_at=timezone.now()+timedelta(hours=2))
  result=scan_ticket(v,d,value,event_id=self.e.pk)
  self.assertEqual(result['status'],'unknown')
  self.assertEqual(Ticket.objects.filter(used_at__isnull=False).count(),0)
 def test_forged_unknown_reference_rejected_before_lookup(self):
  import json,base64,uuid
  from core.tickets import verify_qr_data
  ticket=self.paid_ticket();value=ticket_token(ticket);version,payload,signature=value.split('.')
  data=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
  data['r']='GL-'+str(uuid.uuid4()).upper()
  forged=base64.urlsafe_b64encode(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).decode().rstrip('=')
  with self.assertNumQueries(0):
   with self.assertRaises(ValidationError) as caught:verify_qr_data(version+'.'+forged+'.'+signature)
  self.assertEqual(caught.exception.code,'signature_invalid')

class RegistrationPurchaseVerificationTests(TestCase):
 setUp=PlatformTests.setUp
 def test_preregistration_requires_email_only(self):
  event=Event.objects.create(name='Soirée',slug='email-only',starts_at=timezone.now()+timedelta(days=5),venue='Salle',address='Bordeaux',capacity=10,price_cents=1000,published=True,sales_open=True)
  user=User.objects.create_user(username='student@grandlebrun.com',email='student@grandlebrun.com',password='Vx9!qRm2',phone='+33612345679',email_verified=True,phone_verified=False)
  registration=pre_register(user,event,'adult')
  self.assertEqual(registration.user,user)

 def test_new_account_does_not_get_created_for_short_password(self):
  response=self.client.post('/inscription/',{'first_name':'Camille','last_name':'Martin','email':'camille@grandlebrun.com','phone':'0612345679','password1':'Short7!','password2':'Short7!'})
  self.assertEqual(response.status_code,200)
  self.assertFalse(User.objects.filter(email='camille@grandlebrun.com').exists())
  self.assertEqual(Challenge.objects.count(),0)

 def test_signup_eight_character_password_queues_email_only(self):
  response=self.client.post('/inscription/',{'first_name':'Camille','last_name':'Martin','email':'camille@grandlebrun.com','phone':'0612345679','password1':'Vx9!qRm2','password2':'Vx9!qRm2'})
  self.assertEqual(response.status_code,302)
  user=User.objects.get(email='camille@grandlebrun.com')
  self.assertFalse(user.email_verified)
  self.assertFalse(user.phone_verified)
  self.assertEqual(list(Challenge.objects.values_list('kind',flat=True)),['email'])

 def test_login_uses_email_label(self):
  self.assertContains(self.client.get('/connexion/'),'Adresse mail')

 def test_account_verification_page_does_not_verify_phone(self):
  user=User.objects.create_user(username='student@grandlebrun.com',email='student@grandlebrun.com',password='Vx9!qRm2')
  self.client.force_login(user)
  response=self.client.get('/verification/')
  self.assertNotContains(response,'Code reçu par SMS')
  self.assertNotContains(response,'Renvoyer le SMS')

 def test_inscription_form_has_no_event_code(self):
  event=Event.objects.create(name='Soirée',slug='no-event-code',starts_at=timezone.now()+timedelta(days=5),venue='Salle',address='Bordeaux',capacity=10,price_cents=1000,published=True)
  user=User.objects.create_user(username='student@grandlebrun.com',email='student@grandlebrun.com',password='Vx9!qRm2',email_verified=True)
  self.client.force_login(user)
  response=self.client.get('/evenement/'+event.slug+'/inscription/')
  self.assertEqual(response.status_code,200)
  self.assertNotContains(response,'Classe')
  self.assertNotContains(response,'Code événement')
  self.assertContains(response,'Ton inscription')

 def test_sms_code_is_requested_during_purchase_not_signup(self):
  event=Event.objects.create(name='Soirée test',slug='purchase-sms',starts_at=timezone.now()+timedelta(days=5),venue='Salle',address='Bordeaux',capacity=10,price_cents=1000,published=True,is_test=True)
  user=User.objects.create_user(username='buyer@grandlebrun.com',email='buyer@grandlebrun.com',password='Vx9!qRm2',phone='+33612345679',email_verified=True)
  pre_register(user,event,'adult')
  self.client.force_login(user)
  response=self.client.post('/evenement/'+event.slug+'/billets/',{'participants':''})
  self.assertEqual(response.status_code,200)
  self.assertContains(response,'CONFIRME LES TÉLÉPHONES')
  challenge=Challenge.objects.get(user=user,kind='sms')
  sms_job=Job.objects.get(key=f'challenge:{challenge.pk}')
  code=sms_job.payload['code']
  token=response.context['phone_verification']['token']
  response=self.client.post('/evenement/'+event.slug+'/billets/',{'action':'verify_phones','phone_state':token,'phone_code_'+str(user.pk):code})
  self.assertIsNotNone(response.context['quote'])
  user.refresh_from_db();self.assertTrue(user.phone_verified)

 def test_simulated_sumup_link_issues_test_tickets_without_payment(self):
  from .payments import create_test_checkout_order
  event=Event.objects.create(name='Soirée TEST',slug='sumup-test',starts_at=timezone.now()+timedelta(days=5),venue='Salle',address='Bordeaux',capacity=10,price_cents=1500,published=True,is_test=True)
  registration=pre_register(self.u,event,'adult')
  order=create_test_checkout_order(self.u,event,[registration.pk])
  self.assertTrue(order.is_test);self.assertEqual(order.status,'creating');self.assertIn('/paiement-test/',order.checkout_url)
  self.assertEqual(Ticket.objects.count(),0)
  self.client.force_login(self.u)
  response=self.client.post('/paiement-test/'+str(order.pk)+'/',{'action':'success'})
  self.assertEqual(response.status_code,302)
  order.refresh_from_db();self.assertEqual(order.status,'test')
  ticket=Ticket.objects.get(line__order=order);self.assertTrue(ticket.is_test)
  self.assertFalse(order.checkout_id)
  self.assertEqual(set(Job.objects.filter(payload__ticket=str(ticket.pk)).values_list('kind',flat=True)),{'test_ticket_sms','test_email'})

 def test_test_checkout_rechecks_phone_before_issuing_a_ticket(self):
  from .payments import create_test_checkout_order
  event=Event.objects.create(name='Soirée TEST',slug='sumup-test-phone-change',starts_at=timezone.now()+timedelta(days=5),venue='Salle',address='Bordeaux',capacity=10,price_cents=1500,published=True,is_test=True)
  registration=pre_register(self.u,event,'adult')
  order=create_test_checkout_order(self.u,event,[registration.pk])
  self.u.phone_verified=False;self.u.save(update_fields=['phone_verified'])
  self.client.force_login(self.u)
  response=self.client.post('/paiement-test/'+str(order.pk)+'/',{'action':'success'})
  self.assertEqual(response.status_code,302)
  order.refresh_from_db();self.assertEqual(order.status,'creating')
  self.assertFalse(Ticket.objects.filter(line__order=order).exists())

class ManualAuthenticityTests(TestCase):
 setUp=PlatformTests.setUp
 reg=PlatformTests.reg
 paid_ticket=PlatformTests.paid_ticket
 def test_manual_reference_requires_and_verifies_signature(self):
  import json
  ticket=self.paid_ticket();v=User.objects.create_user(username='manual-validator',role='validator');Assignment.objects.create(user=v,event=self.e)
  device=Device.objects.create(user=v,approved=True,expires_at=timezone.now()+timedelta(hours=2))
  self.client.force_login(v);session=self.client.session;session['device_id']=str(device.pk);session.save()
  body={'event':self.e.pk,'value':ticket.reference}
  response=self.client.post('/validation/scan/',json.dumps(body),content_type='application/json')
  self.assertEqual(response.json()['status'],'unknown');ticket.refresh_from_db();self.assertIsNone(ticket.used_at)
  body.update(price='15,00',signature='0'*64)
  response=self.client.post('/validation/scan/',json.dumps(body),content_type='application/json')
  self.assertEqual(response.status_code,400);self.assertEqual(response.json()['status'],'invalid')
  body['signature']=ticket_token(ticket).rsplit('.',1)[-1]
  response=self.client.post('/validation/scan/',json.dumps(body),content_type='application/json')
  self.assertEqual(response.json()['status'],'accepted')

class MoneyDisplayTests(TestCase):
 setUp=PlatformTests.setUp
 reg=PlatformTests.reg
 def test_order_displays_cents_without_rounding(self):
  self.e.price_cents=1550;self.e.save();order=create_order(self.u,self.e,[self.reg().pk])
  self.client.force_login(self.u)
  self.assertContains(self.client.get('/commande/'+str(order.pk)+'/'),'15.50 €')

class OVHSmsTests(TestCase):
 @override_settings(SMS_PROVIDER='ovh',OVH_SMS_ACCOUNT='sms-test',OVH_SMS_LOGIN='glorieux',OVH_SMS_PASSWORD='secret-test',OVH_SMS_SENDER='SNOOPUPIO')
 def test_ovh_sends_credentials_in_post_body_and_checks_acceptance(self):
  from unittest.mock import patch,Mock
  from core.delivery import send_sms,sms_ready
  self.assertTrue(sms_ready())
  response=Mock(status_code=200);response.json.return_value={'status':100,'SmsIds':['123']}
  with patch('core.delivery.requests.post',return_value=response) as post:
   self.assertEqual(send_sms('+33612345678','Glorieux - Code : 123456'),'123')
  self.assertNotIn('secret-test',post.call_args.args[0]);self.assertEqual(post.call_args.kwargs['data']['password'],'secret-test');self.assertFalse(post.call_args.kwargs['allow_redirects'])
 @override_settings(SMS_PROVIDER='ovh',OVH_SMS_ACCOUNT='sms-test',OVH_SMS_LOGIN='glorieux',OVH_SMS_PASSWORD='secret-test')
 def test_ovh_provider_refusal_is_not_success(self):
  from unittest.mock import patch,Mock
  from core.delivery import send_sms
  response=Mock(status_code=200);response.json.return_value={'status':201,'message':'refused'}
  with patch('core.delivery.requests.post',return_value=response):
   with self.assertRaises(RuntimeError):send_sms('+33612345678','Test')

class TestModeTests(TestCase):
 setUp=PlatformTests.setUp
 reg=PlatformTests.reg
 def issue(self):
  from core.payments import create_test_order
  root=User.objects.create_superuser(username='test-root',email='testroot@example.com',password='Secret!2026')
  self.e.is_test=True;self.e.save()
  return create_test_order(root,self.e,self.u)
 def test_only_superadmin_issues_fake_ticket(self):
  from core.payments import create_test_order
  self.e.is_test=True;self.e.save()
  with self.assertRaises(PermissionDenied):create_test_order(self.u,self.e,self.u)
 def test_test_orders_hold_no_capacity_or_payment(self):
  ticket=self.issue()
  self.assertTrue(ticket.is_test);self.assertEqual(ticket.line.order.status,'test');self.assertFalse(ticket.line.held)
  self.assertTrue(ticket.reference.startswith('GL-T-'))
 def test_test_ticket_refused_when_event_returns_to_real_mode(self):
  ticket=self.issue();v=User.objects.create_user(username='tv',role='validator');Assignment.objects.create(user=v,event=self.e)
  device=Device.objects.create(user=v,approved=True,expires_at=timezone.now()+timedelta(hours=3))
  self.e.is_test=False;self.e.save()
  result=scan_ticket(v,device,ticket_token(ticket),event_id=self.e.pk)
  self.assertEqual(result['status'],'invalid');ticket.refresh_from_db();self.assertIsNone(ticket.used_at)
 def test_real_payments_blocked_in_test_mode(self):
  self.e.is_test=True;self.e.save()
  with self.assertRaises(ValidationError):create_order(self.u,self.e,[self.reg().pk])

class ConsultativeScanTests(TestCase):
 setUp=PlatformTests.setUp
 reg=PlatformTests.reg
 paid_ticket=PlatformTests.paid_ticket
 def test_consult_does_not_register_entry(self):
  ticket=self.paid_ticket();v=User.objects.create_user(username='consult',role='validator');Assignment.objects.create(user=v,event=self.e)
  d=Device.objects.create(user=v,approved=True,expires_at=timezone.now()+timedelta(hours=2))
  result=scan_ticket(v,d,ticket_token(ticket),event_id=self.e.pk,mode='consult')
  self.assertEqual(result['status'],'valid');ticket.refresh_from_db();self.assertIsNone(ticket.used_at)
  result=scan_ticket(v,d,ticket_token(ticket),event_id=self.e.pk,mode='entry')
  self.assertEqual(result['status'],'accepted');ticket.refresh_from_db();self.assertIsNotNone(ticket.used_at)
  from core.models import Audit
  self.assertEqual(Audit.objects.filter(action='scan_accepted').latest('pk').device,d)

class EntryReportTests(TestCase):
 setUp=PlatformTests.setUp
 reg=PlatformTests.reg
 paid_ticket=PlatformTests.paid_ticket
 def test_entry_time_in_html_csv_and_scoped_pdf(self):
  ticket=self.paid_ticket();org=User.objects.create_user(username='report',role='organizer',is_staff=True);Assignment.objects.create(user=org,event=self.e)
  device=Device.objects.create(user=org,approved=True,expires_at=timezone.now()+timedelta(hours=2))
  scan_ticket(org,device,ticket_token(ticket),event_id=self.e.pk);ticket.refresh_from_db()
  self.client.force_login(org);stamp=timezone.localtime(ticket.used_at).strftime('%d/%m/%Y %H:%M:%S')
  self.assertContains(self.client.get('/gestion/?event='+str(self.e.pk)),stamp)
  response=self.client.get('/gestion/export/?event='+str(self.e.pk));self.assertIn(stamp,response.content.decode())
  response=self.client.get('/gestion/pdf/?event='+str(self.e.pk));self.assertEqual(response.status_code,200);self.assertTrue(response.content.startswith(b'%PDF'))
  outsider=User.objects.create_user(username='outsider',role='organizer',email='outsider@example.com');self.client.force_login(outsider)
  self.assertEqual(self.client.get('/gestion/pdf/?event='+str(self.e.pk)).status_code,404)
 def test_sms_balance_visible_only_to_superadmin(self):
  from core.delivery import record_balance
  record_balance('1321.35')
  a=User.objects.create_user(username='balance-admin',role='admin',is_staff=True)
  self.client.force_login(a);self.assertNotContains(self.client.get('/gestion/'),'COMPTEUR SMS OVH')
  root=User.objects.create_superuser(username='balance-root',email='balance@example.com',password='Secret!2026');self.client.force_login(root)
  self.assertContains(self.client.get('/gestion/'),'COMPTEUR SMS OVH');self.assertContains(self.client.get('/gestion/'),'1321,35')

class PaymentIsolationTests(TestCase):
 setUp=PlatformTests.setUp
 reg=PlatformTests.reg
 @override_settings(PAYMENTS_ENABLED=True,SUMUP_API_KEY='test',SUMUP_MERCHANT_CODE='merchant')
 def test_event_switched_to_test_cannot_start_checkout(self):
  from core.payments import begin_checkout
  from unittest.mock import patch
  order=create_order(self.u,self.e,[self.reg().pk]);self.e.is_test=True;self.e.save()
  with patch('core.payments.requests.post') as post:
   with self.assertRaises(ValidationError):begin_checkout(order)
   post.assert_not_called()
 def test_test_order_never_becomes_paid(self):
  from core.payments import create_test_order
  root=User.objects.create_superuser(username='guardroot',email='guard@example.com',password='Secret!2026');self.e.is_test=True;self.e.save()
  ticket=create_test_order(root,self.e,self.u);order=ticket.line.order;order.checkout_id='fake';order.save()
  with self.assertRaises(ValidationError):confirm_payment(order.pk,{'id':'fake','checkout_reference':str(order.pk),'status':'PAID','amount':15,'currency':'EUR'})
  order.refresh_from_db();self.assertEqual(order.status,'test')
 @override_settings(SMS_PROVIDER='ovh',OVH_SMS_ACCOUNT='test',OVH_SMS_LOGIN='test',OVH_SMS_PASSWORD='test',OVH_SMS_SENDER='',OVH_SMS_USE_SHORT_NUMBER=True)
 def test_otp_ready_does_not_mean_ticket_link_ready(self):
  from core.delivery import sms_ready,ticket_sms_ready
  self.assertTrue(sms_ready());self.assertFalse(ticket_sms_ready())

class OVHPlainResponseTests(TestCase):
 @override_settings(SMS_PROVIDER='ovh',OVH_SMS_ACCOUNT='sms-test',OVH_SMS_LOGIN='glorieux',OVH_SMS_PASSWORD='secret-test',OVH_SMS_SENDER='DIGITALEVEN',OVH_SMS_USE_SHORT_NUMBER=False)
 def test_successful_plain_response_updates_balance_without_retry(self):
  from unittest.mock import patch,Mock
  from core.delivery import send_sms
  from core.models import SmsBalance
  response=Mock(status_code=200,text='OK\n1320.35\n825513998\n');response.json.side_effect=ValueError()
  with patch('core.delivery.requests.post',return_value=response) as post:self.assertEqual(send_sms('+33612345678','Glorieux - Code : 123456'),'825513998')
  self.assertEqual(post.call_count,1);self.assertEqual(str(SmsBalance.objects.get(pk=1).credits),'1320.35')

class SelfDeviceApprovalTests(TestCase):
 def check(self,is_super):
  user=User.objects.create_user(username='device-root' if is_super else 'device-validator',email='device-root@example.com' if is_super else 'device-v@example.com',is_superuser=is_super,is_staff=is_super,role='admin' if is_super else 'validator')
  device=Device.objects.create(user=user,expires_at=timezone.now()+timedelta(hours=12))
  self.client.force_login(user);session=self.client.session;session['device_id']=str(device.pk);session.save()
  response=self.client.post('/validation/',{'action':'authorize_self'});device.refresh_from_db();return response,device
 def test_superadmin_explicitly_approves_own_phone(self):
  response,device=self.check(True);self.assertEqual(response.status_code,302);self.assertTrue(device.approved)
 def test_validator_cannot_self_approve(self):
  response,device=self.check(False);self.assertEqual(response.status_code,403);self.assertFalse(device.approved)

class WelcomeScanTests(TestCase):
 setUp=PlatformTests.setUp
 reg=PlatformTests.reg
 paid_ticket=PlatformTests.paid_ticket
 def test_entry_returns_identity_and_server_entry_time(self):
  ticket=self.paid_ticket();v=User.objects.create_user(username='welcome',role='validator');Assignment.objects.create(user=v,event=self.e)
  d=Device.objects.create(user=v,approved=True,expires_at=timezone.now()+timedelta(hours=2))
  result=scan_ticket(v,d,ticket_token(ticket),event_id=self.e.pk)
  self.assertEqual(result['first_name'],'Camille');self.assertEqual(result['last_name'],'Martin');self.assertIn('bienvenue Camille',result['message'])
  ticket.refresh_from_db();self.assertEqual(result['entry_at'],ticket.used_at.isoformat())

class EmailAttachmentTests(TestCase):
 def test_wire_email_contains_png_and_pdf_attachments(self):
  from unittest.mock import patch,Mock
  from email import policy
  from email.parser import BytesParser
  from core.delivery import send_email
  client=Mock();client.send_email.return_value={'MessageId':'test-id'}
  with patch('core.delivery.boto3.client',return_value=client):
   self.assertEqual(send_email('test@example.com','Billet TEST','Votre billet',attachments=[('billet.png',b'png-data','image/png'),('billet.pdf',b'%PDF-test','application/pdf')]),'test-id')
  raw=client.send_email.call_args.kwargs['Content']['Raw']['Data'];message=BytesParser(policy=policy.default).parsebytes(raw)
  self.assertEqual([p.get_content_type() for p in message.iter_attachments()],['image/png','application/pdf'])
  self.assertEqual([p.get_filename() for p in message.iter_attachments()],['billet.png','billet.pdf'])
 def test_payment_queues_individual_email_beside_sms(self):
  PlatformTests.setUp(self)
  registration=pre_register(self.u,self.e,'adult');order=create_order(self.u,self.e,[registration.pk]);order.checkout_id='mail';order.save()
  confirm_payment(order.pk,{'id':'mail','checkout_reference':str(order.pk),'status':'PAID','amount':15,'currency':'EUR'})
  self.assertEqual(Job.objects.filter(kind='ticket_email',destination=self.u.email).count(),1)
  self.assertEqual(Job.objects.filter(kind='ticket',destination=self.u.phone).count(),1)
