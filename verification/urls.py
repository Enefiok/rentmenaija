from django.urls import path
from . import views

urlpatterns = [
    path("start/", views.verification_start, name="verification_start"),
    path("selfie/", views.verification_selfie, name="verification_selfie"),
    path("result/", views.verification_result, name="verification_result"),
]