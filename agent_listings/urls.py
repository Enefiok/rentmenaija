# agent_listings/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('start/', views.start_agent_listing, name='start-agent-listing'),
    path('<int:draft_id>/', views.update_agent_property_draft, name='update-agent-draft'),
    path('<int:draft_id>/upload-image/', views.upload_agent_property_image, name='upload-agent-image'),
    path('<int:draft_id>/confirm-location/', views.confirm_agent_location_and_geocode, name='confirm-agent-location'),
    path('<int:draft_id>/submit/', views.submit_agent_property_for_review, name='submit-agent-for-review'),
    
]