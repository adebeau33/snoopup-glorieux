from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.views import PasswordResetView
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Job
from .services import limited
import secrets
class QueuedResetForm(PasswordResetForm):
 def clean_email(self):
  email=self.cleaned_data['email'].strip().lower()
  if limited('reset-address:'+email,3,3600):raise ValidationError('Trop de demandes. Réessayez plus tard.')
  return email
 def send_mail(self,subject_template_name,email_template_name,context,from_email,to_email,html_email_template_name=None):
  from django.template.loader import render_to_string
  subject=''.join(render_to_string(subject_template_name,context).splitlines())
  body=render_to_string(email_template_name,context)
  Job.objects.create(key='reset:'+secrets.token_urlsafe(24),kind='reset',destination=to_email,payload={'subject':subject,'body':body},next_at=timezone.now())
class LimitedResetView(PasswordResetView):
 form_class=QueuedResetForm
 def form_valid(self,form):
  if limited('reset-ip:'+self.request.META.get('REMOTE_ADDR',''),15,3600):
   form.add_error(None,'Trop de demandes. Réessayez plus tard.');return self.form_invalid(form)
  return super().form_valid(form)
