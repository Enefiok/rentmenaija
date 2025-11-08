# hotels/views.py

import cloudinary.uploader
import requests
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.conf import settings
from .models import HotelListing, HotelFeature, RoomType
from .serializers import HotelListingSerializer, RoomTypeSerializer, HotelFeatureSerializer


def geocode_address(address):
    """Geocode Nigerian address using Nominatim."""
    base_url = "https://nominatim.openstreetmap.org/search"  # ✅ Fixed: no spaces
    params = {
        'q': address.strip(),
        'format': 'json',
        'limit': 1,
        'countrycodes': 'ng',  # ✅ Lowercase 'ng' for Nominatim
    }
    headers = {
        'User-Agent': 'RentMeNaija/1.0'  # ✅ No email
    }
    try:
        response = requests.get(base_url, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            results = response.json()
            if results:
                loc = results[0]
                return {'lat': float(loc['lat']), 'lng': float(loc['lon'])}
    except Exception as e:
        print("Geocoding error:", e)
    return None


# === STEP 1: Start Hotel Draft ===
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_hotel_listing(request):
    hotel = HotelListing.objects.create(owner=request.user, status='draft')
    serializer = HotelListingSerializer(hotel)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


# === STEP 2: Update Basic Info ===
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_hotel_basic_info(request, hotel_id):
    hotel = get_object_or_404(HotelListing, id=hotel_id, owner=request.user, status='draft')
    serializer = HotelListingSerializer(hotel, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# === STEP 3: Set Location ===
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_hotel_location(request, hotel_id):
    hotel = get_object_or_404(HotelListing, id=hotel_id, owner=request.user, status='draft')
    address = request.data.get('address')
    if not address:
        return Response({"error": "Address is required"}, status=status.HTTP_400_BAD_REQUEST)

    coords = geocode_address(address)
    if not coords:
        return Response({
            "error": "Could not find coordinates for this address."
        }, status=status.HTTP_400_BAD_REQUEST)

    hotel.address = address
    hotel.latitude = coords['lat']
    hotel.longitude = coords['lng']
    hotel.save(update_fields=['address', 'latitude', 'longitude'])

    try:
        from listings.utils import reverse_geocode
        loc_data = reverse_geocode(hotel.latitude, hotel.longitude)
        hotel.city = loc_data.get('city', '') or ''
        hotel.state = loc_data.get('state', '') or ''
        hotel.save(update_fields=['city', 'state'])
    except Exception as e:
        print(f"[Hotel] Reverse geocoding failed: {e}")

    return Response({
        "address": hotel.address,
        "latitude": hotel.latitude,
        "longitude": hotel.longitude,
        "city": hotel.city,
        "state": hotel.state
    }, status=status.HTTP_200_OK)


# === STEP 4: Add Room Type ===
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_hotel_room_type(request, hotel_id):
    hotel = get_object_or_404(HotelListing, id=hotel_id, owner=request.user, status='draft')
    serializer = RoomTypeSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(hotel=hotel)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# === STEP 4b: Upload Room Image ===
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_room_image(request, hotel_id, room_id):
    hotel = get_object_or_404(HotelListing, id=hotel_id, owner=request.user, status='draft')
    room = get_object_or_404(RoomType, id=room_id, hotel=hotel)
    
    if 'image' not in request.FILES:
        return Response({"error": "Image file required"}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        upload_result = cloudinary.uploader.upload(
            request.FILES['image'],
            folder=f"rentmenaija/hotel_rooms/{hotel.id}/{room.id}/"
        )
        room.images.append(upload_result['secure_url'])
        room.save(update_fields=['images'])
        return Response({"image_url": upload_result['secure_url']}, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({"error": "Image upload failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# === STEP 5: Add Hotel Features ===
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_hotel_features(request, hotel_id):
    hotel = get_object_or_404(HotelListing, id=hotel_id, owner=request.user, status='draft')
    features_data = request.data.get('features', [])
    if not isinstance(features_data, list):
        return Response({"error": "Features must be a list"}, status=status.HTTP_400_BAD_REQUEST)

    hotel.features.all().delete()
    for feat in features_data:
        HotelFeature.objects.create(
            hotel=hotel,
            category=feat.get('category', 'additional'),
            name=feat.get('name', ''),
            is_custom=feat.get('is_custom', False)
        )
    return Response({"message": "Features saved successfully"}, status=status.HTTP_200_OK)


# === STEP 6: Sign Legal Declarations ===
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def sign_hotel_declarations(request, hotel_id):
    hotel = get_object_or_404(HotelListing, id=hotel_id, owner=request.user, status='draft')
    
    required_fields = [
        'is_owner_or_representative',
        'details_accurate',
        'assume_responsibility_for_fraud',
        'agrees_to_escrow_process',
        'digital_signature'
    ]
    
    for field in required_fields:
        if field not in request.data:
            return Response({"error": f"{field} is required"}, status=status.HTTP_400_BAD_REQUEST)
    
    hotel.is_owner_or_representative = request.data['is_owner_or_representative']
    hotel.details_accurate = request.data['details_accurate']
    hotel.assume_responsibility_for_fraud = request.data['assume_responsibility_for_fraud']
    hotel.agrees_to_escrow_process = request.data['agrees_to_escrow_process']
    hotel.digital_signature = request.data['digital_signature']
    hotel.signed_at = timezone.now()
    hotel.save(update_fields=[
        'is_owner_or_representative', 'details_accurate', 'assume_responsibility_for_fraud',
        'agrees_to_escrow_process', 'digital_signature', 'signed_at'
    ])
    
    return Response({"message": "Declarations signed successfully"}, status=status.HTTP_200_OK)


# === STEP 7: Submit for Approval ===
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_hotel_for_review(request, hotel_id):
    hotel = get_object_or_404(HotelListing, id=hotel_id, owner=request.user, status='draft')

    # Must have signed declarations
    if not getattr(hotel, 'signed_at', None):
        return Response({"error": "Legal declarations must be signed before submission"}, status=status.HTTP_400_BAD_REQUEST)

    # ✅ UPDATED: Include bank details in required fields validation
    required = [
        'name', 'property_type', 'phone', 'address', 'latitude', 'longitude',
        'owner_bank_name', 'owner_account_number', 'owner_account_name'
    ]
    missing = [field for field in required if not getattr(hotel, field, None)]
    if missing:
        return Response({"error": "Missing required fields", "missing": missing}, status=status.HTTP_400_BAD_REQUEST)

    # ✅ NEW: Validate bank account number format
    if hotel.owner_account_number:
        if not hotel.owner_account_number.isdigit():
            return Response({"error": "Account number must contain only digits"}, status=400)
        if len(hotel.owner_account_number) != 10:
            return Response({"error": "Account number must be exactly 10 digits"}, status=400)

    if not hotel.room_types.exists():
        return Response({"error": "At least one room type is required"}, status=status.HTTP_400_BAD_REQUEST)

    hotel.status = 'submitted'
    # ✅ UPDATED: Include bank details in save
    hotel.save(update_fields=[
        'status',
        'owner_bank_name', 'owner_account_number', 'owner_account_name'
    ])
    return Response({
        "message": "✅ Your hotel listing has been submitted successfully and is now awaiting admin approval.",
        "listing_id": hotel.id
    }, status=status.HTTP_200_OK)


# === PUBLIC VIEWS ===
@api_view(['GET'])
@permission_classes([AllowAny])
def hotel_list(request):
    queryset = HotelListing.objects.filter(status='approved').order_by('-published_at')
    city = request.query_params.get('city')
    state = request.query_params.get('state')
    property_type = request.query_params.get('property_type')
    price_min = request.query_params.get('price_min')
    price_max = request.query_params.get('price_max')

    if city:
        queryset = queryset.filter(city__iexact=city.strip())
    if state:
        queryset = queryset.filter(state__iexact=state.strip())
    if property_type:
        queryset = queryset.filter(property_type=property_type.strip())
    if price_min or price_max:
        room_qs = RoomType.objects.all()
        if price_min:
            room_qs = room_qs.filter(price_per_night__gte=price_min)
        if price_max:
            room_qs = room_qs.filter(price_per_night__lte=price_max)
        hotel_ids = room_qs.values_list('hotel_id', flat=True).distinct()
        queryset = queryset.filter(id__in=hotel_ids)

    serializer = HotelListingSerializer(queryset, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def hotel_detail(request, hotel_id):
    try:
        if request.user.is_authenticated:
            hotel = HotelListing.objects.get(id=hotel_id, owner=request.user)
        else:
            hotel = HotelListing.objects.get(id=hotel_id, status='approved')
    except HotelListing.DoesNotExist:
        return Response({"error": "Hotel not found."}, status=status.HTTP_404_NOT_FOUND)

    serializer = HotelListingSerializer(hotel)
    return Response(serializer.data, status=status.HTTP_200_OK)


# In hotels/views.py, after other views

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_hotel_image(request, hotel_id):
    hotel = get_object_or_404(HotelListing, id=hotel_id, owner=request.user, status='draft')
    
    if 'image' not in request.FILES:
        return Response({"error": "Image file required"}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        upload_result = cloudinary.uploader.upload(
            request.FILES['image'],
            folder=f"rentmenaija/hotel_drafts/{hotel.id}/"
        )
        # Append to hotel.images (you'll need to add this field to model)
        if not hasattr(hotel, 'images'):
            hotel.images = []
        hotel.images.append(upload_result['secure_url'])
        hotel.save(update_fields=['images'])
        
        return Response({"image_url": upload_result['secure_url']}, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({"error": "Image upload failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)