from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path
from core import views
from core.auth import RateAuthenticationForm
from core.reset import LimitedResetView
admin.site.login_form=RateAuthenticationForm
urlpatterns=[
 path('',views.home,name='home'),path('partage.png',views.social_image),path('evenement/<slug:slug>/visuel.png',views.social_image),path('evenement/<slug:slug>/',views.event_detail,name='event'),
 path('inscription/',views.register,name='register'),
 path('connexion/',auth.LoginView.as_view(authentication_form=RateAuthenticationForm),name='login'),
 path('deconnexion/',auth.LogoutView.as_view(),name='logout'),
 path('verification/',views.verify,name='verify'),path('verification/email/<int:user_id>/<str:token>/',views.verify_email),
 path('mon-espace/',views.account,name='account'),
 path('evenement/<slug:slug>/preinscription/',views.preregister,name='preregister'),
 path('evenement/<slug:slug>/billets/',views.buy,name='buy'),
 path('commande/<uuid:order_id>/',views.order_detail,name='order'),
 path('paiement/notification/',views.payment_notification),
 path('q/<str:value>/',views.public_scan),
 path('billet/<str:token>/',views.ticket_download,name='ticket'),
 path('billet/<str:token>/<str:fmt>/',views.ticket_download),
 path('validation/',views.validation,name='validation'),path('validation/scan/',views.scan,name='scan'),
 path('gestion/',views.dashboard,name='dashboard'),path('gestion/export/',views.export_participants,name='export'),path('confidentialite/',views.privacy,name='privacy'),
 path('mot-de-passe/',LimitedResetView.as_view(),name='password_reset'),
 path('mot-de-passe/envoye/',auth.PasswordResetDoneView.as_view(),name='password_reset_done'),
 path('mot-de-passe/<uidb64>/<token>/',auth.PasswordResetConfirmView.as_view(),name='password_reset_confirm'),
 path('mot-de-passe/modifie/',auth.PasswordResetCompleteView.as_view(),name='password_reset_complete'),
 path('admin/',admin.site.urls)]
