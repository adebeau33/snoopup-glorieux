from datetime import timedelta
from django.test import TestCase,override_settings
from django.utils import timezone
from django.core.exceptions import ValidationError,PermissionDenied
from .models import User,Event,SchoolClass,Registration,Order,OrderLine,Ticket,Device,Assignment,Job,Challenge
from .services import normalize_phone,school_email,issue_challenge,verify_challenge,pre_register
from .payments import create_order,confirm_payment
from .tickets import ticket_token,scan_ticket

class PlatformTests(TestCase):
 def setUp(self):
  self.u=User.objects.create_user(username='eleve@grandlebrun.com',email='eleve@grandlebrun.com',password='UnMotDePasse!672',first_name='Camille',last_name='Martin',phone='+33612345678',email_verified=True,phone_verified=True)
  self.e=Event.objects.create(name='Soirée',slug='soiree',access_code='GL2026',starts_at=timezone.now()+timedelta(days=30),venue='Salle',address='Bordeaux',capacity=2,price_cents=1500,published=True,sales_open=True)
  self.c=SchoolClass.objects.create(name='Terminale A')
 def reg(self,u=None):
  return pre_register(u or self.u,self.e,self.c,'adult','GL2026')
 def test_email_exact_domain(self):
  self.assertEqual(school_email(' X@GrandLebrun.com '),'x@grandlebrun.com')
  for email in ['x@gmail.com','x@grandlebrun.com.evil.fr','x@sub.grandlebrun.com']:
   with self.assertRaises(ValidationError):school_email(email)
 def test_phone_normalization(self):
  self.assertEqual(normalize_phone('06 12 34 56 78'),'+33612345678')
 def test_requires_both_verifications(self):
  for field in ['email_verified','phone_verified']:
   setattr(self.u,field,False)
   with self.assertRaises(ValidationError):self.reg()
   setattr(self.u,field,True)
 def test_declaration_and_event_code(self):
  for choice in ['', 'adult,minor']:
   with self.assertRaises(ValidationError):pre_register(self.u,self.e,self.c,choice,'GL2026')
  with self.assertRaises(ValidationError):pre_register(self.u,self.e,self.c,'adult','wrong')
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
  e=Event.objects.create(name='Concurrent',slug='concurrent',access_code='C',starts_at=timezone.now()+timedelta(days=2),venue='Salle',address='Bordeaux',capacity=1,price_cents=1000,published=True,sales_open=True)
  c=SchoolClass.objects.create(name='Classe test')
  regs=[]
  for i in range(8):
   u=User.objects.create_user(username=f'u{i}',email=f'u{i}@grandlebrun.com',phone=f'+3360000000{i}',email_verified=True,phone_verified=True)
   regs.append(pre_register(u,e,c,'adult','C'))
  def buy(r):
   connections.close_all()
   try:create_order(r.user,e,[r.pk]);return 'ok'
   except ValidationError:return 'full'
   finally:connections.close_all()
  with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(buy,regs))
  self.assertEqual(results.count('ok'),1);self.assertEqual(OrderLine.objects.filter(held=True).count(),1)
 def test_simultaneous_scans_accept_once(self):
  e=Event.objects.create(name='Scans',slug='scans',access_code='S',starts_at=timezone.now()+timedelta(days=2),venue='Salle',address='Bordeaux',capacity=1,price_cents=1000,published=True,sales_open=True)
  c=SchoolClass.objects.create(name='Classe scans');u=User.objects.create_user(username='s',email='s@grandlebrun.com',phone='+33612345678',email_verified=True,phone_verified=True)
  r=pre_register(u,e,c,'adult','S');o=create_order(u,e,[r.pk]);o.checkout_id='c';o.save()
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
  self.assertEqual(image.width,1000)
