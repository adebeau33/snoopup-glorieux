from django import forms
from django.contrib.auth.forms import UserCreationForm,AuthenticationForm
from .models import User,SchoolClass
from .services import school_email,normalize_phone,DECLARATIONS

class RegisterForm(UserCreationForm):
 email=forms.EmailField(label='Email scolaire',help_text='Uniquement @grandlebrun.com. Un email de confirmation vous sera envoyé sur cette boîte mail.')
 phone=forms.CharField(label='Téléphone portable',help_text='Votre numéro personnel, pour le code SMS et votre billet.')
 first_name=forms.CharField(label='Prénom',max_length=150)
 last_name=forms.CharField(label='Nom',max_length=150)
 class Meta:model=User;fields=['first_name','last_name','email','phone','password1','password2']
 def clean_email(self):
  value=school_email(self.cleaned_data['email'])
  if User.objects.filter(email__iexact=value).exists():raise forms.ValidationError('Cette adresse est déjà utilisée.')
  return value
 def clean_phone(self):
  value=normalize_phone(self.cleaned_data['phone'])
  if User.objects.filter(phone=value).exists():raise forms.ValidationError('Ce numéro est déjà utilisé.')
  return value
 def save(self,commit=True):
  u=super().save(False);u.username=self.cleaned_data['email'];u.email=self.cleaned_data['email'];u.phone=self.cleaned_data['phone']
  if commit:u.save()
  return u

class PreRegisterForm(forms.Form):
 code=forms.CharField(label='Code événement',max_length=80)
 school_class=forms.ModelChoiceField(label='Classe',queryset=SchoolClass.objects.filter(active=True))
 declaration=forms.ChoiceField(label='À la date de la soirée',choices=list(DECLARATIONS.items()),widget=forms.RadioSelect)

class DeviceForm(forms.Form):
 name=forms.CharField(label='Nom de ce téléphone',max_length=120)

class BuyForm(forms.Form):
 participants=forms.CharField(label='Emails scolaires des autres participants',required=False,widget=forms.Textarea(attrs={'rows':3,'placeholder':'Un email par ligne'}),help_text='Chaque participant doit avoir validé son compte et sa propre préinscription. Votre billet est ajouté automatiquement.')
