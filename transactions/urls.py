# transactions/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('lease-payment/', views.initiate_lease_payment, name='initiate_lease_payment'),
    # Booking endpoints
    path('save/', views.save_booking, name='save_booking'),
    path('', views.get_bookings, name='get_bookings'), # GET /api/transactions/ lists bookings
    path('<int:booking_id>/confirm/', views.confirm_booking, name='confirm_booking'),
    path('<int:booking_id>/cancel/', views.cancel_booking, name='cancel_booking'),
    path('<int:booking_id>/refund/', views.request_refund, name='request_refund'),
    # ✅ NEW: Fund Release endpoint
    path('<int:booking_id>/release-funds/', views.release_funds, name='release-funds'),
    # Add other transaction-related URLs here in the future
    # path('lease-payment/<int:id>/', views.get_lease_payment_status, name='get_lease_payment_status'),
]