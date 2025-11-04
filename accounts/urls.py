# accounts/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='api_register'),
    path('login/', views.login, name='api_login'),
    path('profile/', views.profile, name='api_profile'),
    path('verify-email/<str:token>/', views.verify_email, name='verify-email'),
    path('phone/', views.update_user_phone, name='update-phone'),  # ← Added
]