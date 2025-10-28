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
    Initiate Youverify verification.
    Automatically detects Sandbox vs Live mode.
    """
    user = request.user

    # ✅ Get user's phone number safely
    phone = getattr(user, 'phone', None) or getattr(user, 'phone_number', None)
    if not phone:
        return Response(
            {"error": "Phone number is required for identity verification."},
            status=status.HTTP_400_BAD_REQUEST
        )

    email = user.email
    reference = f"user_{user.id}_{int(timezone.now().timestamp())}"

    # ✅ Detect environment from BASE_URL
    is_sandbox = "sandbox" in settings.YV_BASE_URL.lower()

    # ✅ Use correct token header (not Bearer)
    headers = {
        "Token": f"{settings.YV_API_KEY}",
        "Content-Type": "application/json",
    }

    if is_sandbox:
        # 🧪 Sandbox testing endpoint — mock verification only
        url = f"{settings.YV_BASE_URL}/identity/ng/nin"
        payload = {
            "id": "12345678901",   # fake test NIN
            "isSubjectConsent": True
        }
    else:
        # 🌍 Live environment — hosted verification
        url = f"{settings.YV_BASE_URL}/hosted/verifications"
        payload = {
            "reference": reference,
            "email": email,
            "phoneNumber": str(phone),
            "redirectUrl": "https://rentmenaija.com/verify/success",
            "callbackUrl": "https://rentmenaija-a4ed.onrender.com/api/verify/webhook/",
        }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        # Try parsing JSON safely
        try:
            data = response.json()
        except json.JSONDecodeError:
            return Response({
                "error": "Youverify returned a non-JSON response.",
                "status_code": response.status_code,
                "raw_response": response.text,
            }, status=status.HTTP_502_BAD_GATEWAY)

        # ✅ Success
        if response.status_code == 200:
            if is_sandbox:
                # Direct mock verification result
                return Response({
                    "environment": "sandbox",
                    "data": data
                }, status=status.HTTP_200_OK)

            # Live environment: redirect link for hosted verification
            if data.get("data", {}).get("verificationUrl"):
                return Response({
                    "environment": "live",
                    "verification_url": data["data"]["verificationUrl"]
                }, status=status.HTTP_200_OK)

        # ⚠️ Unexpected response
        return Response({
            "error": "Unexpected response from Youverify.",
            "status_code": response.status_code,
            "details": data,
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
    Receive verification result from Youverify (for live environment).
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
