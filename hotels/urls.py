# hotels/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Owner Flow (Authenticated)
    path('start/', views.start_hotel_listing, name='start-hotel'),
    path('<int:hotel_id>/basic/', views.update_hotel_basic_info, name='update-basic'),
    path('<int:hotel_id>/location/', views.set_hotel_location, name='set-location'),
    path('<int:hotel_id>/rooms/', views.add_hotel_room_type, name='add-room'),
    path('<int:hotel_id>/features/', views.add_hotel_features, name='add-features'),
    path('<int:hotel_id>/submit/', views.submit_hotel_for_review, name='submit-hotel'),

    # Public Views (Guests)
    path('', views.hotel_list, name='hotel-list'),
    path('<int:hotel_id>/', views.hotel_detail, name='hotel-detail'),
]