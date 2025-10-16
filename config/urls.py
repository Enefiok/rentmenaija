"""
URL configuration for Rent Me Naija project.

The `urlpatterns` list routes URLs to views.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from django.shortcuts import redirect


# Option A: Simple homepage message
def home(request):
    return HttpResponse("Welcome to RentmeNaija! 🚀")


# Option B: Redirect root URL to /api/ (uncomment if preferred)
# def home(request):
#     return redirect('/api/')


urlpatterns = [
    # Root/Homepage
    path('', home, name='home'),

    # Admin Interface
    path('admin/', admin.site.urls),

    # Custom API Endpoints (Register, Login, Profile, Verify Email)
    path('api/', include('accounts.urls')),

    path('api/listings/', include('listings.urls')),

    path('api/agent-listings/', include('agent_listings.urls')),
]

# Serve static and media files during development ONLY
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)