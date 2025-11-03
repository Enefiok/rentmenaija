# payments/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('pay/', views.initiate_payment, name='initiate_payment'),
    path('webhook/', views.squad_webhook, name='squad_webhook'),
]