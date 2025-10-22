# verification/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('initiate/', views.initiate_verification, name='initiate-verification'),
    path('webhook/', views.verification_webhook, name='verification-webhook'),
]