"""Run explicitly: manage.py test core.tests_load --noinput. No production data used."""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from django.test import TransactionTestCase
from django.db import connections,connection
from django.utils import timezone
from .models import User,Event,SchoolClass,Registration,Order,OrderLine,Ticket,Device,Assignment
from .tickets import ticket_token,scan_ticket
class ValidationLoadTests(TransactionTestCase):
 def test_2000_entries_eight_phones(self):
  with connection.cursor() as cursor:cursor.execute('PRAGMA journal_mode=WAL')
  now=timezone.now()
  e=Event.objects.create(name='Charge isolée',slug='charge',starts_at=now+timedelta(days=1),access_code='X',venue='Test',address='Test',capacity=2000,price_cents=1000,published=True,sales_open=True)
  c=SchoolClass.objects.create(name='Test charge')
  users=User.objects.bulk_create([User(username=f'charge{i}',email=f'charge{i}@grandlebrun.com',phone=f'+336{i:08}',first_name='Test',last_name=str(i),email_verified=True,phone_verified=True) for i in range(2000)])
  regs=Registration.objects.bulk_create([Registration(user=u,event=e,school_class=c,declaration='adult',declaration_text='Test isolé') for u in users])
  o=Order.objects.create(buyer=users[0],event=e,status='paid',total_cents=2000000)
  lines=OrderLine.objects.bulk_create([OrderLine(order=o,registration=r,price_cents=1000) for r in regs])
  tickets=Ticket.objects.bulk_create([Ticket(line=line) for line in lines])
  values=[ticket_token(t) for t in tickets]
  v=User.objects.create(username='valideur-charge',role='validator');Assignment.objects.create(user=v,event=e)
  d=Device.objects.create(user=v,approved=True,expires_at=now+timedelta(hours=12))
  def run(value):
   started=time.monotonic()
   try:
    result=scan_ticket(v,d,value,event_id=e.pk)
    return result['status'],time.monotonic()-started
   finally:connections.close_all()
  start=time.monotonic()
  with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(run,values))
  elapsed=time.monotonic()-start;durations=sorted(r[1] for r in results)
  self.assertEqual(sum(r[0]=='accepted' for r in results),2000)
  self.assertEqual(Ticket.objects.filter(used_at__isnull=False).count(),2000)
  print(f'\nCHARGE : 2000 validations / 8 threads / {elapsed:.2f}s ; p95 {durations[1899]:.3f}s ; aucune double entrée')
