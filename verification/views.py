import requests
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.utils import timezone


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_verification(request):
    """
    Initiate Youverify identity verification for the logged-in user.
    """
    user = request.user

    # Get phone — adjust field name if needed (e.g., 'phone_number')
    phone = getattr(user, 'phone', None) or getattr(user, 'phone_number', None)
    if not phone:
        return Response({
            "error": "Phone number is required for identity verification."
        }, status=status.HTTP_400_BAD_REQUEST)

    email = user.email
    reference = f"user_{user.id}_{int(timezone.now().timestamp())}"

    url = f"{settings.YV_BASE_URL}/hosted/verifications"
    headers = {
        'Authorization': f'Bearer {settings.YV_API_KEY}',
        'Content-Type': 'application/json'
    }
    payload = {
        "reference": reference,
        "email": email,
        "phoneNumber": str(phone),
        "redirectUrl": "https://rentmenaija.com/verify/success",
        "callbackUrl": "https://rentmenaija-a4ed.onrender.com/api/verify/webhook/"
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('data', {}).get('verificationUrl'):
            # Optional: save reference to user (if you add the field later)
            return Response({
                "verification_url": data['data']['verificationUrl']
            }, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Invalid response from Youverify."}, status=status.HTTP_502_BAD_GATEWAY)

    except requests.exceptions.RequestException as e:
        return Response({
            "error": "Failed to connect to Youverify.",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(['POST'])
def verification_webhook(request):
    """
    Receive verification result from Youverify.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    reference = data.get('reference')
    status_code = data.get('status')

    if not reference or not reference.startswith('user_'):
        return JsonResponse({"error": "Invalid reference"}, status=400)

    try:
        user_id = int(reference.split('_')[1])
        from accounts.models import User
        user = User.objects.get(id=user_id)
    except (ValueError, User.DoesNotExist):
        return JsonResponse({"error": "User not found"}, status=404)

    if status_code == "completed":
        user.is_identity_verified = True
        user.identity_verified_at = timezone.now()
        user.save(update_fields=['is_identity_verified', 'identity_verified_at'])

    # You can also handle "failed" if needed

    return JsonResponse({"status": "ok"}, status=200)