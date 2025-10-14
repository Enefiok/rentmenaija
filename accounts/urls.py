# accounts/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='api_register'),
    path('login/', views.login, name='api_login'),            # ← Added login endpoint
    path('profile/', views.profile, name='api_profile'),      # Keep profile
    path('verify-email/<str:token>/', views.verify_email, name='verify-email'),
]