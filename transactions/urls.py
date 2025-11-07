from django.urls import path
from . import views

urlpatterns = [
    path('lease-payment/', views.initiate_lease_payment, name='initiate_lease_payment'),
    # Add other transaction-related URLs here in the future
    # path('lease-payment/<int:id>/', views.get_lease_payment_status, name='get_lease_payment_status'),
]