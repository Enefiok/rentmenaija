# listings/views.py

import cloudinary.uploader
import random
import requests
from decouple import config
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from .models import PropertyDraft, Property
from .serializers import PropertyDraftSerializer, PropertyDetailSerializer, PropertyListingSerializer


# === Mock URLs (✅ CLEANED: no extra spaces!) ===
MOCK_IMAGE_URLS = [
    "https://via.placeholder.com/800x600.png?text=Living+Room",
    "https://via.placeholder.com/800x600.png?text=Kitchen",
    "https://via.placeholder.com/800x600.png?text=Bedroom",
    "https://via.placeholder.com/800x600.png?text=Bathroom",
    "https://via.placeholder.com/800x600.png?text=Exterior",
]


def geocode_address(address):
    """
    Geocode Nigerian address using Nominatim (OpenStreetMap).
    Falls back to None if failed.
    """
    print(f"Geocoding request for: {address}")

    base_url = "https://nominatim.openstreetmap.org/search"  # ✅ FIXED: no extra spaces
    params = {
        'q': address.strip(),
        'format': 'json',
        'limit': 1,
        'countrycodes': 'NG',  # Only Nigeria
    }
    headers = {
        'User-Agent': 'RentMeNaija/1.0 (elongate371@gmail.com)'  # Required by Nominatim
    }

    try:
        response = requests.get(base_url, params=params, headers=headers, timeout=10)
        print("Nominatim URL:", response.url)
        print("Status Code:", response.status_code)

        if response.status_code == 200:
            results = response.json()
            if results:
                loc = results[0]
                return {
                    'lat': float(loc['lat']),
                    'lng': float(loc['lon'])
                }
            else:
                print("No geocoding results found.")
        else:
            print(f"Geocoding failed. Status: {response.status_code}")

    except Exception as e:
        print("Geocoding error:", e)

    return None


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_property_listing(request):
    """Start a new property listing draft"""
    draft = PropertyDraft.objects.create(user=request.user)
    serializer = PropertyDraftSerializer(draft)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_property_draft(request, draft_id):
    """Update any field in the draft"""
    draft = get_object_or_404(PropertyDraft, id=draft_id, user=request.user)
    serializer = PropertyDraftSerializer(draft, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_property_image(request, draft_id):
    """Upload one image — uses Cloudinary, falls back to mock if unavailable"""
    draft = get_object_or_404(PropertyDraft, id=draft_id, user=request.user)
    file = request.FILES.get('image')
    if not file:
        return Response({"error": "No image provided"}, status=status.HTTP_400_BAD_REQUEST)

    allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
    if file.content_type not in allowed_types:
        return Response({
            "error": "Invalid file type. Supported: JPEG, PNG, WebP."
        }, status=status.HTTP_400_BAD_REQUEST)

    if file.size > 10 * 1024 * 1024:
        return Response({
            "error": "File too large. Maximum 10MB allowed."
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        upload_result = cloudinary.uploader.upload(
            file,
            folder="rentmenaija/property_drafts",
            resource_type="image",
            overwrite=False,
            unique_filename=True
        )
        image_url = upload_result.get('secure_url')
        if image_url:
            draft.add_image_url(image_url)
            return Response({"url": image_url}, status=status.HTTP_201_CREATED)
    except Exception as e:
        print(f"Cloudinary upload failed: {e}")

    mock_url = random.choice(MOCK_IMAGE_URLS)
    filename_base = file.name.rsplit('.', 1)[0] if '.' in file.name else file.name
    safe_text = filename_base.replace('+', '%20').replace(' ', '+')
    mock_url_with_name = f"{mock_url.split('?')[0]}?text={safe_text}"

    draft.add_image_url(mock_url_with_name)
    return Response({
        "url": mock_url_with_name,
        "filename": file.name,
        "size": file.size,
        "content_type": file.content_type,
        "uploaded": True,
        "service": "mock-development-fallback"
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirm_location_and_geocode(request, draft_id):
    """Auto-fill latitude and longitude from address"""
    draft = get_object_or_404(PropertyDraft, id=draft_id, user=request.user)
    address = request.data.get('address')
    if not address:
        return Response({"error": "Address is required"}, status=400)

    coords = geocode_address(address)
    if not coords:
        return Response({
            "error": "Could not find coordinates for this address. Please try being more specific."
        }, status=400)

    draft.address = address
    draft.latitude = coords['lat']
    draft.longitude = coords['lng']
    draft.save()

    return Response({
        "address": address,
        "latitude": coords['lat'],
        "longitude": coords['lng']
    }, status=200)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_property_for_review(request, draft_id):
    """Submit the draft for admin approval"""
    draft = get_object_or_404(PropertyDraft, id=draft_id, user=request.user)

    required_fields = [
        'title', 'monthly_rent', 'phone_number', 'description',
        'address', 'latitude', 'longitude', 'images'
    ]
    missing = [f for f in required_fields if not getattr(draft, f)]
    if missing:
        return Response({
            "error": "Missing required fields",
            "missing": missing
        }, status=400)

    agreements = [
        draft.is_owner_or_representative,
        draft.details_accurate,
        draft.responsible_for_fraud,
        draft.allow_escrow,
        draft.signature
    ]
    if not all(agreements):
        return Response({
            "error": "You must accept all terms and sign the agreement."
        }, status=400)

    if draft.latitude is not None and draft.longitude is not None:
        try:
            from .utils import reverse_geocode
            location_data = reverse_geocode(draft.latitude, draft.longitude)
            draft.city = location_data['city']
            draft.state = location_data['state']
        except Exception as e:
            print(f"Reverse geocoding failed during submission: {e}")

    draft.signed_at = timezone.now()
    draft.submitted_for_review = True
    draft.save()

    Property.objects.get_or_create(draft=draft)

    return Response({
        "message": "✅ Your listing has been submitted successfully and is now awaiting admin approval."
    }, status=200)


@api_view(['GET'])
@permission_classes([AllowAny])
def property_detail(request, property_id):
    try:
        property_obj = Property.objects.select_related('draft').get(
            id=property_id,
            status='approved'
        )
    except Property.DoesNotExist:
        return Response({
            "error": "Property not found or not yet approved."
        }, status=status.HTTP_404_NOT_FOUND)

    serializer = PropertyDetailSerializer(property_obj)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def property_list(request):
    queryset = Property.objects.select_related('draft').filter(status='approved')

    city = request.query_params.get('city')
    state = request.query_params.get('state')
    property_type = request.query_params.get('property_type')
    price_min = request.query_params.get('price_min')
    price_max = request.query_params.get('price_max')

    if city:
        queryset = queryset.filter(draft__city__iexact=city.strip())
    if state:
        queryset = queryset.filter(draft__state__iexact=state.strip())
    if property_type:
        queryset = queryset.filter(draft__property_type=property_type.strip())
    if price_min:
        queryset = queryset.filter(draft__monthly_rent__gte=price_min)
    if price_max:
        queryset = queryset.filter(draft__monthly_rent__lte=price_max)

    queryset = queryset.order_by('-published_at')
    serializer = PropertyListingSerializer(queryset, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)