from django.contrib import admin,messages
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from .models import User,Event,SchoolClass,Assignment,Registration,Order,OrderLine,Ticket,Device,Audit,Job
from .services import events_for

admin.site.site_header='GLORIEUX · Administration'
admin.site.site_title='Glorieux'
admin.site.index_title='Gestion de la plateforme'

class SuperOnly(admin.ModelAdmin):
 def has_module_permission(self,r):return r.user.is_superuser
 def has_view_permission(self,r,obj=None):return r.user.is_superuser
 def has_add_permission(self,r):return r.user.is_superuser
 def has_change_permission(self,r,obj=None):return r.user.is_superuser
 def has_delete_permission(self,r,obj=None):return r.user.is_superuser

@admin.register(User)
class Users(UserAdmin):
 fieldsets=UserAdmin.fieldsets+(("Glorieux",{'fields':('phone','role','email_verified','phone_verified')}),)
 list_display=['username','first_name','last_name','role','email_verified','phone_verified']
 actions=['approve_admins']
 @admin.action(description='Accorder le rôle administrateur aux comptes sélectionnés')
 def approve_admins(self,r,qs):
  if not r.user.is_superuser:raise PermissionDenied()
  for user in qs.filter(is_superuser=False).exclude(role='admin'):
   user.role='admin';user.is_staff=True;user.save()
   Audit.objects.create(actor=r.user,action='approbation_administrateur',object_id=str(user.pk))
 def get_actions(self,r):
  actions=super().get_actions(r)
  if not r.user.is_superuser:actions.pop('approve_admins',None)
  return actions
 def allowed(self,r):return r.user.is_superuser or r.user.role=='admin'
 def get_queryset(self,r):
  qs=super().get_queryset(r)
  return qs if r.user.is_superuser else qs.filter(role__in=['student','organizer','validator'],is_superuser=False)
 def has_module_permission(self,r):return self.allowed(r)
 def has_view_permission(self,r,obj=None):return self.allowed(r) and (obj is None or r.user.is_superuser or self.get_queryset(r).filter(pk=obj.pk).exists())
 def has_add_permission(self,r):return self.allowed(r)
 def has_change_permission(self,r,obj=None):return self.has_view_permission(r,obj)
 def has_delete_permission(self,r,obj=None):return False
 def get_fieldsets(self,r,obj=None):
  if r.user.is_superuser:return super().get_fieldsets(r,obj)
  if obj is None:return ((None,{'fields':('username','email','first_name','last_name','role','password1','password2')}),)
  return ((None,{'fields':('username','email','first_name','last_name','phone','role','is_active','email_verified','phone_verified')}),)
 def get_readonly_fields(self,r,obj=None):
  return () if r.user.is_superuser else ('email_verified','phone_verified')
 def formfield_for_choice_field(self,db_field,r,**kw):
  if db_field.name=='role' and not r.user.is_superuser:kw['choices']=[c for c in User.ROLE_CHOICES if c[0]!='admin']
  return super().formfield_for_choice_field(db_field,r,**kw)
 def save_model(self,r,obj,form,change):
  from .services import school_email,normalize_phone
  if not r.user.is_superuser and (obj.is_superuser or obj.role=='admin'):raise PermissionDenied()
  if obj.email and obj.role=='student':obj.email=school_email(obj.email)
  if obj.phone:obj.phone=normalize_phone(obj.phone)
  if change:
   old=User.objects.get(pk=obj.pk)
   if old.phone!=obj.phone:obj.phone_verified=False
   if old.email!=obj.email:obj.email_verified=False
  obj.is_staff=obj.is_superuser or obj.role in ['admin','organizer']
  super().save_model(r,obj,form,change)
  Audit.objects.create(actor=r.user,action='modification_compte',object_id=str(obj.pk))

class Scoped(admin.ModelAdmin):
 event_path='event'
 def allowed(self,r):return r.user.is_superuser or r.user.role in ['admin','organizer']
 def get_queryset(self,r):
  qs=super().get_queryset(r)
  if r.user.is_superuser or r.user.role=='admin':return qs
  return qs.filter(**{self.event_path+'__in':events_for(r.user)}) if self.event_path else qs.none()
 def has_module_permission(self,r):return self.allowed(r)
 def has_view_permission(self,r,obj=None):
  return self.allowed(r) and (obj is None or self.get_queryset(r).filter(pk=obj.pk).exists())
 def has_add_permission(self,r):return r.user.is_superuser or r.user.role=='admin'
 def has_change_permission(self,r,obj=None):return self.has_view_permission(r,obj)
 def has_delete_permission(self,r,obj=None):return False
 def formfield_for_foreignkey(self,db_field,r,**kwargs):
  if db_field.name=='event':kwargs['queryset']=events_for(r.user)
  return super().formfield_for_foreignkey(db_field,r,**kwargs)
 def save_model(self,r,obj,form,change):
  if change and not self.has_change_permission(r,obj):raise PermissionDenied()
  super().save_model(r,obj,form,change)
  Audit.objects.create(actor=r.user,action='admin_'+obj._meta.model_name,object_id=str(obj.pk))

@admin.register(Event)
class Events(Scoped):
 event_path='pk'
 list_display=['name','starts_at','capacity','price_cents','published','sales_open']
 prepopulated_fields={'slug':('name',)}
 def get_queryset(self,r):return events_for(r.user)

@admin.register(SchoolClass)
class Classes(Scoped):
 event_path=None
 list_display=['name','active']
 def get_queryset(self,r):return SchoolClass.objects.all() if r.user.is_superuser or r.user.role=='admin' else SchoolClass.objects.none()

@admin.register(Registration)
class Registrations(Scoped):
 list_display=['user','event','school_class','declaration','created_at']
 list_filter=['event','school_class','declaration']
 search_fields=['user__first_name','user__last_name','user__email']
 readonly_fields=['user','event','school_class','declaration','declaration_text','declaration_version','created_at']
 def has_add_permission(self,r):return False

@admin.register(Assignment)
class Assignments(Scoped):
 list_display=['user','event']
 def has_change_permission(self,r,obj=None):return r.user.is_superuser or r.user.role=='admin'
 def has_delete_permission(self,r,obj=None):return self.has_change_permission(r,obj)

@admin.register(Order)
class Orders(Scoped):
 list_display=['id','buyer','event','status','total_cents','created_at']
 list_filter=['event','status']
 actions=['reconcile']
 @admin.action(description='Réconcilier auprès de SumUp et résoudre les commandes incertaines')
 def reconcile(self,r,qs):
  from .payments import reconcile_order
  for order in qs[:20]:
   try:reconcile_order(order)
   except Exception:self.message_user(r,'Une commande nécessite une vérification manuelle.',level=messages.WARNING)
  Audit.objects.create(actor=r.user,action='reconciliation_admin',object_id=str(qs.count()))
 readonly_fields=['id','buyer','event','status','total_cents','currency','checkout_id','checkout_url','created_at','updated_at']
 def has_add_permission(self,r):return False

@admin.register(Ticket)
class Tickets(Scoped):
 event_path='line__order__event'
 list_display=['id','participant','active','used_at']
 list_filter=['active','line__order__event']
 readonly_fields=['id','line','used_at','used_by','created_at']
 exclude=['download_token']
 def participant(self,obj):return obj.line.registration.user.get_full_name()
 def has_add_permission(self,r):return False
 # Only cancellation is editable. Reactivation could invalidate accounting; keep paid allocation held.
 def save_model(self,r,obj,form,change):
  if 'active' in form.changed_data and obj.active:raise PermissionDenied('Réémission à traiter séparément par l’organisation.')
  super().save_model(r,obj,form,change)

@admin.register(Device)
class Devices(Scoped):
 event_path=None
 list_display=['name','user','approved','expires_at','created_at']
 readonly_fields=['user','name','created_at']
 def get_queryset(self,r):
  qs=Device.objects.all()
  if r.user.is_superuser or r.user.role=='admin':return qs
  return qs.filter(user__assignment__event__in=events_for(r.user)).distinct()
 def has_add_permission(self,r):return False

@admin.register(Audit)
class Audits(Scoped):
 list_display=['created_at','actor','event','action','object_id']
 list_filter=['event','action']
 def has_add_permission(self,r):return False
 def has_change_permission(self,r,obj=None):return False

@admin.register(Job)
class Jobs(Scoped):
 event_path=None
 list_display=['created_at','kind','state','attempts','last_error']
 list_filter=['kind','state']
 fields=['kind','destination','state','attempts','next_at','last_error','provider_id','created_at']
 readonly_fields=fields
 actions=['retry']
 def get_queryset(self,r):return Job.objects.all() if r.user.is_superuser or r.user.role=='admin' else Job.objects.none()
 def has_add_permission(self,r):return False
 def has_change_permission(self,r,obj=None):return r.user.is_superuser or r.user.role=='admin'
 @admin.action(description='Relancer les envois échoués (hors envois incertains)')
 def retry(self,r,qs):
  n=qs.filter(state='failed').update(state='pending',attempts=0,next_at=timezone.now())
  Audit.objects.create(actor=r.user,action='relance_envois',object_id=str(n));self.message_user(r,f'{n} envoi(s) remis en attente.')
