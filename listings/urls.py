# listings/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Draft management (authenticated)
    path('start/', views.start_property_listing, name='start-listing'),
    path('<int:draft_id>/', views.update_property_draft, name='update-draft'),
    path('<int:draft_id>/upload-image/', views.upload_property_image, name='upload-image'),
    path('<int:draft_id>/confirm-location/', views.confirm_location_and_geocode, name='confirm-location'),
    path('<int:draft_id>/submit/', views.submit_property_for_review, name='submit-for-review'),
    
    # ✅ Public endpoints (unauthenticated)
    path('', views.property_list, name='property-list'),          # ← ADD THIS LINE
    path('detail/<int:property_id>/', views.property_detail, name='property-detail'),
]