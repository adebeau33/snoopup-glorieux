from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from .services import limited
class RateAuthenticationForm(AuthenticationForm):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs)
  self.fields['username'].label='Adresse mail'
 def clean(self):
  username=self.cleaned_data.get('username','').strip().lower()
  self.cleaned_data['username']=username
  ip=self.request.META.get('REMOTE_ADDR','') if self.request else ''
  if limited('login-user:'+username,15,900) or limited('login-ip:'+ip,60,900):raise ValidationError('Trop de tentatives. Réessayez dans 15 minutes.')
  return super().clean()
