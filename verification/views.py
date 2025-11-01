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
    Initiate Youverify HOSTED verification flow (works in both sandbox and live).
    Redirects user to Youverify's UI for ID entry + selfie.
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

    headers = {
        "Authorization": f"Bearer {settings.YV_API_KEY}",
        "Content-Type": "application/json",
    }

    # ✅ CORRECT ENDPOINT: /hosted/verifications (not /kyc/initiate)
    url = f"{settings.YV_BASE_URL}/hosted/verifications"

    # 🔧 TRIMMED URLs – no trailing spaces!
    redirect_url = "https://rentmenaija.com/verify/success"
    webhook_url = "https://rentmenaija-a4ed.onrender.com/api/verify/webhook/"

    payload = {
        "reference": reference,
        "email": email,
        "phoneNumber": str(phone),
        "country": "NG",
        "product_type": "nin",  # User enters NIN on Youverify's page
        "redirectUrl": redirect_url,
        "webhookUrl": webhook_url
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        # Parse response safely
        try:
            data = response.json()
        except json.JSONDecodeError:
            return Response({
                "error": "Youverify returned a non-JSON response.",
                "status_code": response.status_code,
                "raw_response": response.text,
            }, status=status.HTTP_502_BAD_GATEWAY)

        # ✅ Check for successful hosted session creation
        if response.status_code == 200:
            verification_url = data.get("data", {}).get("verificationUrl")
            if verification_url:
                return Response({
                    "verification_url": verification_url,
                    "environment": "sandbox" if "sandbox" in settings.YV_BASE_URL else "live"
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    "error": "Missing verificationUrl in Youverify response.",
                    "details": data
                }, status=status.HTTP_502_BAD_GATEWAY)
        else:
            return Response({
                "error": "Youverify API request failed.",
                "status_code": response.status_code,
                "details": data
            }, status=status.HTTP_400_BAD_REQUEST)

    except requests.exceptions.RequestException as e:
        return Response({
            "error": "Failed to connect to Youverify.",
            "details": str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(["POST"])
def verification_webhook(request):
    """
    Handle callback from Youverify (used in both sandbox and live).
    """
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # Extract data from webhook payload
    event = data.get("event")
    if event != "identity.completed":
        return JsonResponse({"status": "ignored", "reason": "non-completion event"}, status=200)

    verification_data = data.get("data", {})
    reference = verification_data.get("reference")
    status_code = verification_data.get("status")

    # Fallback: try top-level reference if not in data
    if not reference:
        reference = data.get("reference")

    if not reference or not str(reference).startswith("user_"):
        return JsonResponse({"error": "Invalid or missing reference"}, status=400)

    try:
        user_id = int(str(reference).split("_")[1])
        from accounts.models import User
        user = User.objects.get(id=user_id)
    except (ValueError, User.DoesNotExist, IndexError):
        return JsonResponse({"error": "User not found"}, status=404)

    # ✅ Mark user as verified only if all checks passed
    all_passed = verification_data.get("allValidationPassed", False)
    if status_code == "found" and all_passed:
        user.is_identity_verified = True
        user.identity_verified_at = timezone.now()
        user.save(update_fields=["is_identity_verified", "identity_verified_at"])

    return JsonResponse({"status": "ok"}, status=200)