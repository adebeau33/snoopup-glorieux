import time
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Case,When,Value,IntegerField
from django.utils import timezone
from core.models import Job,Order
from core.delivery import deliver
from core.payments import reconcile_order
class Command(BaseCommand):
 help='Traite les envois persistants et réconcilie les paiements en attente.'
 def add_arguments(self,p):p.add_argument('--loop',action='store_true')
 def handle(self,*args,**options):
  while True:
   now=timezone.now()
   # A stale worker could have sent before crashing: flag for human review, never silently duplicate.
   Job.objects.filter(state='sending',locked_at__lt=now-timedelta(minutes=5)).update(state='review',last_error='delivery_uncertain')
   deadline=time.monotonic()+90
   for _ in range(30):
    if time.monotonic()>deadline:break
    with transaction.atomic():
     j=Job.objects.filter(state='pending',next_at__lte=timezone.now()).annotate(priority=Case(When(kind__in=['sms','email','reset'],then=Value(0)),default=Value(1),output_field=IntegerField())).order_by('priority','next_at').first()
     if not j:break
     j.state='sending';j.locked_at=timezone.now();j.attempts+=1;j.save()
    try:
     provider=deliver(j);j.state='sent';j.provider_id=provider;j.payload={};j.last_error=''
    except Exception as exc:
     # Persist only exception class, never provider request text (may contain secrets).
     j.last_error=type(exc).__name__
     j.state='failed' if j.attempts>=5 else 'pending'
     j.next_at=timezone.now()+timedelta(seconds=min(3600,60*2**j.attempts))
    j.save()
   payment_deadline=time.monotonic()+40
   for o in Order.objects.filter(status__in=['pending','creating','review']).order_by('updated_at')[:20]:
    if time.monotonic()>payment_deadline:break
    try:reconcile_order(o)
    except Exception:pass
   if not options['loop']:break
   time.sleep(20)
