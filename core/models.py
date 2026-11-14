import secrets,uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q

def token():return secrets.token_urlsafe(32)

class User(AbstractUser):
 ROLE_CHOICES=[('student','Étudiant'),('admin','Administrateur'),('organizer','Organisateur'),('validator','Valideur')]
 email=models.EmailField(unique=True,null=True,blank=True)
 phone=models.CharField(max_length=20,unique=True,null=True,blank=True)
 role=models.CharField(max_length=16,choices=ROLE_CHOICES,default='student')
 email_verified=models.BooleanField(default=False)
 phone_verified=models.BooleanField(default=False)
 def save(self,*args,**kwargs):
  if not self.email:self.email=None
  if not self.phone:self.phone=None
  super().save(*args,**kwargs)

class Event(models.Model):
 name=models.CharField('Nom',max_length=200)
 slug=models.SlugField(unique=True)
 description=models.TextField('Description',blank=True)
 starts_at=models.DateTimeField('Date et heure')
 venue=models.CharField('Lieu',max_length=200)
 address=models.TextField('Adresse')
 organizer_name=models.CharField('Organisateur',max_length=200,blank=True)
 organizer_address=models.CharField('Adresse de l’organisateur',max_length=300,blank=True)
 organizer_contact=models.CharField('Contact organisateur',max_length=200,blank=True)
 capacity=models.PositiveIntegerField('Jauge')
 price_cents=models.PositiveIntegerField('Prix en centimes')
 published=models.BooleanField('Publié',default=False)
 sales_open=models.BooleanField('Ventes ouvertes',default=False)
 is_test=models.BooleanField('Mode TEST (superadmin)',default=False)
 sales_start=models.DateTimeField('Début des ventes',null=True,blank=True)
 sales_end=models.DateTimeField('Fin des ventes',null=True,blank=True)
 class Meta:ordering=['starts_at'];verbose_name='événement'
 def __str__(self):return self.name
 @property
 def price(self):return f'{self.price_cents/100:.2f}'

class Assignment(models.Model):
 user=models.ForeignKey(User,on_delete=models.CASCADE)
 event=models.ForeignKey(Event,on_delete=models.CASCADE)
 class Meta:constraints=[models.UniqueConstraint(fields=['user','event'],name='unique_assignment')];verbose_name='affectation'

class Registration(models.Model):
 DECLARATIONS=[('adult','Majeur à la date de la soirée'),('minor','Mineur, représentants légaux informés')]
 event=models.ForeignKey(Event,on_delete=models.PROTECT)
 user=models.ForeignKey(User,on_delete=models.PROTECT)
 declaration=models.CharField(max_length=8,choices=DECLARATIONS)
 declaration_text=models.TextField()
 declaration_version=models.CharField(max_length=30,default='2026-11-14')
 created_at=models.DateTimeField(auto_now_add=True)
 class Meta:constraints=[models.UniqueConstraint(fields=['event','user'],name='unique_registration')];verbose_name='inscription'
 def __str__(self):return f'{self.user.get_full_name()} — {self.event}'

class Challenge(models.Model):
 user=models.ForeignKey(User,on_delete=models.CASCADE)
 kind=models.CharField(max_length=8)
 digest=models.CharField(max_length=128)
 destination=models.CharField(max_length=254)
 expires_at=models.DateTimeField()
 created_at=models.DateTimeField(auto_now_add=True)
 attempts=models.PositiveSmallIntegerField(default=0)
 consumed=models.BooleanField(default=False)

class Order(models.Model):
 STATUS=[('creating','Création paiement'),('pending','Paiement en attente'),('paid','Payée'),('failed','Échouée'),('review','À examiner'),('test','TEST — sans paiement')]
 id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
 buyer=models.ForeignKey(User,on_delete=models.PROTECT)
 event=models.ForeignKey(Event,on_delete=models.PROTECT)
 status=models.CharField(max_length=16,choices=STATUS,default='creating')
 is_test=models.BooleanField(default=False)
 total_cents=models.PositiveIntegerField()
 currency=models.CharField(max_length=3,default='EUR')
 checkout_id=models.CharField(max_length=100,blank=True,db_index=True)
 checkout_url=models.URLField(blank=True)
 created_at=models.DateTimeField(auto_now_add=True)
 updated_at=models.DateTimeField(auto_now=True)
 class Meta:verbose_name='commande'

class OrderLine(models.Model):
 order=models.ForeignKey(Order,on_delete=models.PROTECT,related_name='lines')
 registration=models.ForeignKey(Registration,on_delete=models.PROTECT)
 price_cents=models.PositiveIntegerField()
 held=models.BooleanField(default=True)
 @property
 def price(self):return f'{self.price_cents/100:.2f}'
 class Meta:constraints=[models.UniqueConstraint(fields=['registration'],condition=Q(held=True),name='unique_held_registration')]

class Ticket(models.Model):
 id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
 line=models.OneToOneField(OrderLine,on_delete=models.PROTECT,related_name='ticket')
 is_test=models.BooleanField(default=False,editable=False)
 download_token=models.CharField(max_length=80,default=token,unique=True,editable=False)
 active=models.BooleanField(default=True)
 used_at=models.DateTimeField(null=True,blank=True)
 used_by=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name='validated_tickets')
 created_at=models.DateTimeField(auto_now_add=True)
 @property
 def reference(self):return ('GL-T-' if self.is_test else 'GL-')+f'{self.line.registration_id:08X}'
 class Meta:verbose_name='billet'

class Device(models.Model):
 id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
 user=models.ForeignKey(User,on_delete=models.CASCADE)
 name=models.CharField('Nom du téléphone',max_length=120,default='Téléphone')
 approved=models.BooleanField('Approuvé',default=False)
 expires_at=models.DateTimeField('Expiration')
 created_at=models.DateTimeField(auto_now_add=True)
 class Meta:verbose_name='appareil de validation'

class Audit(models.Model):
 device=models.ForeignKey(Device,on_delete=models.SET_NULL,null=True,blank=True)
 actor=models.ForeignKey(User,on_delete=models.SET_NULL,null=True)
 event=models.ForeignKey(Event,on_delete=models.SET_NULL,null=True)
 action=models.CharField(max_length=100)
 object_id=models.CharField(max_length=100,blank=True)
 created_at=models.DateTimeField(auto_now_add=True)
 class Meta:verbose_name='journal';ordering=['-created_at']

class Job(models.Model):
 key=models.CharField(max_length=160,unique=True)
 kind=models.CharField(max_length=20)
 destination=models.CharField(max_length=254)
 payload=models.JSONField(default=dict)
 state=models.CharField(max_length=16,default='pending')
 attempts=models.PositiveIntegerField(default=0)
 next_at=models.DateTimeField()
 locked_at=models.DateTimeField(null=True)
 last_error=models.CharField(max_length=100,blank=True)
 provider_id=models.CharField(max_length=120,blank=True)
 created_at=models.DateTimeField(auto_now_add=True)
 class Meta:verbose_name='envoi';ordering=['-created_at']

class RateLimit(models.Model):
 key=models.CharField(max_length=160,unique=True)
 count=models.PositiveIntegerField(default=0)
 reset_at=models.DateTimeField()

class SmsBalance(models.Model):
 credits=models.DecimalField(max_digits=12,decimal_places=2)
 observed_at=models.DateTimeField()
 source=models.CharField(max_length=30,default='ovh')
