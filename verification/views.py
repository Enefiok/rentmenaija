# verification/views.py

import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from .utils.youverify import verify_nin, face_match
import base64

logger = logging.getLogger(__name__)

@csrf_protect
@require_http_methods(["GET", "POST"])
def verification_start(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        nin = request.POST.get("nin", "").strip()

        if not all([email, phone, nin]):
            messages.error(request, "All fields are required.")
            return render(request, "verification/start.html", {"email": email, "phone": phone, "nin": nin})

        if len(nin) != 11 or not nin.isdigit():
            messages.error(request, "NIN must be 11 digits.")
            return render(request, "verification/start.html", {"email": email, "phone": phone, "nin": nin})

        try:
            result = verify_nin(nin)
            if result.get("status") != "success":
                messages.error(request, "NIN not found or invalid. Please check and try again.")
                return render(request, "verification/start.html", {"email": email, "phone": phone, "nin": nin})

            photo = result["data"].get("image")
            if not photo:
                messages.error(request, "No photo found for this NIN.")
                return render(request, "verification/start.html", {"email": email, "phone": phone, "nin": nin})

            request.session["verification_email"] = email
            request.session["verification_phone"] = phone
            request.session["verification_nin"] = nin
            request.session["verification_photo"] = photo

            return redirect("verification_selfie")

        except Exception as e:
            logger.exception("Youverify NIN API error")
            # 🔥 TEMPORARY DEBUG: show real error (remove before production!)
            messages.error(request, f"API Error: {type(e).__name__} - {str(e)[:100]}")
            return render(request, "verification/start.html", {"email": email, "phone": phone, "nin": nin})

    return render(request, "verification/start.html")


@csrf_protect
@require_http_methods(["GET", "POST"])
def verification_selfie(request):
    if "verification_nin" not in request.session:
        return redirect("verification_start")

    if request.method == "POST":
        selfie_data = request.POST.get("selfie", "").strip()
        if not selfie_data:
            messages.error(request, "Please take a selfie.")
            return render(request, "verification/selfie.html")

        if "," in selfie_data:
            selfie_data = selfie_data.split(",")[1]

        try:
            base64.b64decode(selfie_data, validate=True)
        except Exception:
            messages.error(request, "Invalid image data.")
            return render(request, "verification/selfie.html")

        try:
            official_photo = request.session["verification_photo"]
            result = face_match(official_photo, selfie_data)

            match = result.get("match", False)
            confidence = result.get("confidence", 0)

            request.session["verification_match"] = match
            request.session["verification_confidence"] = confidence

            if match and confidence >= 0.85:
                request.session["verification_result"] = "success"
            else:
                request.session["verification_result"] = "failed"

            return redirect("verification_result")

        except Exception as e:
            logger.exception("Youverify Face Match error")
            messages.error(request, f"Face Match Error: {type(e).__name__} - {str(e)[:100]}")
            return render(request, "verification/selfie.html")

    return render(request, "verification/selfie.html")


def verification_result(request):
    result = request.session.get("verification_result")
    if not result:
        return redirect("verification_start")

    confidence = request.session.get("verification_confidence", 0)
    context = {"confidence": confidence}

    if result == "success":
        return render(request, "verification/success.html", context)
    else:
        return render(request, "verification/failure.html", context)