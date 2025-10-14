from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from decouple import config
import requests
import random
from django.utils import timezone  # ← For auto-setting signed_at

from .models import AgentPropertyDraft, AgentProperty  # ✅ Added AgentProperty import
from .serializers import AgentPropertyDraftSerializer


# === Load Env Vars from .env ===
try:
    HOSTINGIER_API_KEY = config('HOSTINGIER_API_KEY')
    HOSTINGIER_UPLOAD_URL = config('HOSTINGIER_UPLOAD_URL')
    HOSTINGIER_CONFIGURED = bool(HOSTINGIER_API_KEY) and bool(HOSTINGIER_UPLOAD_URL)
except Exception as e:
    print(f"Error loading Hostingier config: {e}")
    HOSTINGIER_CONFIGURED = False


# === Mock URLs for Development (✅ Fixed: No leading/trailing spaces) ===
MOCK_IMAGE_URLS = [
    "https://via.placeholder.com/800x600.png?text=Living+Room",
    "https://via.placeholder.com/800x600.png?text=Kitchen",
    "https://via.placeholder.com/800x600.png?text=Bedroom",
    "https://via.placeholder.com/800x600.png?text=Bathroom",
    "https://via.placeholder.com/800x600.png?text=Exterior",
]


# === 1. Start a new agent listing draft ===
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_agent_listing(request):
    """
    Creates a new draft linked to the authenticated agent.
    """
    draft = AgentPropertyDraft.objects.create(agent=request.user)
    serializer = AgentPropertyDraftSerializer(draft)
    return Response(serializer.data, status=201)


# === 2. View or Update basic details of the draft ===
@api_view(['GET', 'PUT', 'PATCH'])  # ✅ Supports viewing and partial/full updates
@permission_classes([IsAuthenticated])
def update_agent_property_draft(request, draft_id):
    """
    - GET: Retrieve the draft (for viewing)
    - PUT/PATCH: Partially or fully update an existing draft (owned by the agent).
    """
    draft = get_object_or_404(AgentPropertyDraft, id=draft_id, agent=request.user)

    if request.method == 'GET':
        serializer = AgentPropertyDraftSerializer(draft)
        return Response(serializer.data)

    # Handle PUT/PATCH updates
    serializer = AgentPropertyDraftSerializer(draft, data=request.data, partial=True)
    if serializer.is_valid():
        # Auto-set signed_at if digital_signature is provided and not already set
        if serializer.validated_data.get('digital_signature') and not draft.signed_at:
            draft.signed_at = timezone.now()
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)


# === 3. Upload image to the property draft via Hostingier (Backend Upload) ===
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_agent_property_image(request, draft_id):
    """
    Securely upload an image through Django to Hostingier.
    - Validates file type and size
    - Uses secret API key
    - Falls back to mock URL if Hostingier fails
    """
    draft = get_object_or_404(AgentPropertyDraft, id=draft_id, agent=request.user)

    file = request.FILES.get('image')
    if not file:
        return Response({"error": "No image provided"}, status=400)

    # Validate file type
    allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
    if file.content_type not in allowed_types:
        return Response({
            "error": "Invalid file type. Supported: JPEG, PNG, WebP."
        }, status=400)

    # Validate file size (< 10MB)
    if file.size > 10 * 1024 * 1024:
        return Response({
            "error": "File too large. Maximum 10MB allowed."
        }, status=400)

    # Try to upload to Hostingier if configured
    if HOSTINGIER_CONFIGURED:
        try:
            headers = {'Authorization': f'Bearer {HOSTINGIER_API_KEY}'}
            files = {'file': (file.name, file.file, file.content_type)}
            response = requests.post(
                HOSTINGIER_UPLOAD_URL,
                headers=headers,
                files=files,
                timeout=30
            )

            if response.status_code in [200, 201]:
                data = response.json()
                image_url = data.get('url') or data.get('data', {}).get('url')
                if image_url:
                    images = draft.images or []
                    images.append(image_url)
                    draft.images = images
                    draft.save()

                    return Response({
                        "message": "Image uploaded successfully",
                        "url": image_url,
                        "images": draft.images
                    }, status=201)
                print("Hostingier responded but no URL found:", data)

            else:
                print("Hostingier upload failed:", response.status_code, response.text)

        except Exception as e:
            print(f"Error connecting to Hostingier: {e}")

    # ✨ Fallback: Use mock image URL
    mock_url = random.choice(MOCK_IMAGE_URLS).strip()
    filename_base = file.name.rsplit('.', 1)[0] if '.' in file.name else file.name
    safe_text = filename_base.replace('+', '%20').replace(' ', '+')
    mock_url_with_name = f"{mock_url.split('?')[0]}?text={safe_text}"

    images = draft.images or []
    images.append(mock_url_with_name)
    draft.images = images
    draft.save()

    return Response({
        "message": "Image added (mock used - Hostingier not available)",
        "url": mock_url_with_name,
        "images": draft.images
    }, status=201)


# === 4. Confirm location and save geocoordinates ===
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirm_agent_location_and_geocode(request, draft_id):
    """
    Save latitude and longitude after frontend geocoding.
    Optionally validate or enrich address here in the future.
    """
    draft = get_object_or_404(AgentPropertyDraft, id=draft_id, agent=request.user)

    latitude = request.data.get('latitude')
    longitude = request.data.get('longitude')
    address = request.data.get('address', draft.address)

    if latitude is None or longitude is None:
        return Response({"error": "Latitude and longitude are required."}, status=400)

    try:
        draft.latitude = float(latitude)
        draft.longitude = float(longitude)
        draft.address = address
        draft.save()
    except (ValueError, TypeError):
        return Response({"error": "Invalid latitude or longitude."}, status=400)

    return Response({
        "message": "Location saved successfully",
        "address": draft.address,
        "latitude": draft.latitude,
        "longitude": draft.longitude
    }, status=200)


# === 5. Submit draft for admin review ===
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_agent_property_for_review(request, draft_id):
    """
    Final step: Mark draft as submitted for review.
    Validates required fields before submission.
    """
    draft = get_object_or_404(AgentPropertyDraft, id=draft_id, agent=request.user)

    # Required fields check
    errors = []

    if not draft.landlord_name:
        errors.append("landlord_name is required.")
    if not draft.landlord_phone:
        errors.append("landlord_phone is required.")
    if not draft.title:
        errors.append("title is required.")
    if draft.monthly_rent is None:
        errors.append("monthly_rent is required.")
    if not draft.address:
        errors.append("address is required.")
    if draft.latitude is None or draft.longitude is None:
        errors.append("Valid location (latitude/longitude) is required.")
    if not draft.images:
        errors.append("At least one image is required.")
    if not draft.is_authorised_to_list:
        errors.append("You must confirm you're authorized to list for the landlord.")
    if not draft.details_accurate:
        errors.append("You must confirm that all details are accurate.")
    if not draft.assume_responsibility_for_fraud:
        errors.append("You must accept responsibility for fraudulent listings.")
    if not draft.agrees_to_escrow_process:
        errors.append("You must agree to the escrow process.")

    if errors:
        return Response({"errors": errors}, status=400)

    # All good — submit!
    draft.submitted_for_review = True
    draft.save()

    # ✅ CRITICAL: Create AgentProperty so it appears in admin review queue
    AgentProperty.objects.get_or_create(draft=draft)

    return Response({
        "message": "Your listing has been submitted for review.",
        "submitted_at": draft.updated_at.isoformat()
    }, status=200)