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
    Initiate Youverify verification (auto-detects Sandbox vs Live mode).
    """
    user = request.user

    # ✅ Safely get user's phone number
    phone = getattr(user, 'phone', None) or getattr(user, 'phone_number', None)
    if not phone:
        return Response(
            {"error": "Phone number is required for identity verification."},
            status=status.HTTP_400_BAD_REQUEST
        )

    email = user.email or "noemail@rentmenaija.com"
    reference = f"user_{user.id}_{int(timezone.now().timestamp())}"

    # ✅ Detect environment from BASE_URL
    is_sandbox = "sandbox" in settings.YV_BASE_URL.lower()

    headers = {
        "Authorization": f"Bearer {settings.YV_API_KEY}",
        "Content-Type": "application/json",
    }

    if is_sandbox:
        # 🧪 Sandbox mock endpoint
        url = f"{settings.YV_BASE_URL}/identity/ng/nin"
        payload = {
            "id": "11111111111",      # ✅ Approved sandbox NIN test ID
            "isSubjectConsent": True  # Required for sandbox calls
        }
    else:
        # 🌍 Live hosted verification
        url = f"{settings.YV_BASE_URL}/hosted/verifications"
        payload = {
            "reference": reference,
            "email": email,
            "phoneNumber": str(phone),
            "redirectUrl": "https://rentmenaija.com/verify/success",
            "callbackUrl": "https://rentmenaija-a4ed.onrender.com/api/verify/webhook/"
        }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        # Try to parse JSON safely
        try:
            data = response.json()
        except json.JSONDecodeError:
            return Response({
                "error": "Youverify returned a non-JSON response.",
                "status_code": response.status_code,
                "raw_response": response.text,
            }, status=status.HTTP_502_BAD_GATEWAY)

        # ✅ Sandbox success
        if is_sandbox:
            if response.status_code == 200:
                return Response({
                    "environment": "sandbox",
                    "message": "Mock verification completed successfully.",
                    "data": data
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    "error": "Sandbox verification failed.",
                    "status_code": response.status_code,
                    "details": data
                }, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Live verification success
        if not is_sandbox and data.get("data", {}).get("verificationUrl"):
            return Response({
                "environment": "live",
                "verification_url": data["data"]["verificationUrl"]
            }, status=status.HTTP_200_OK)

        # ⚠️ Unexpected
        return Response({
            "error": "Unexpected response from Youverify.",
            "status_code": response.status_code,
            "details": data
        }, status=status.HTTP_502_BAD_GATEWAY)

    except requests.exceptions.RequestException as e:
        return Response({
            "error": "Failed to connect to Youverify.",
            "details": str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(["POST"])
def verification_webhook(request):
    """
    Handle callback from Youverify (for live environment only).
    """
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    reference = data.get("reference")
    status_code = data.get("status")

    if not reference or not reference.startswith("user_"):
        return JsonResponse({"error": "Invalid reference"}, status=400)

    try:
        user_id = int(reference.split("_")[1])
        from accounts.models import User
        user = User.objects.get(id=user_id)
    except (ValueError, User.DoesNotExist):
        return JsonResponse({"error": "User not found"}, status=404)

    if status_code == "completed":
        user.is_identity_verified = True
        user.identity_verified_at = timezone.now()
        user.save(update_fields=["is_identity_verified", "identity_verified_at"])

    return JsonResponse({"status": "ok"}, status=200)
