# verification/utils/youverify.py

import requests
from django.conf import settings

def verify_nin(nin: str):
    # ✅ CORRECT endpoint (includes /api)
    url = f"{settings.YV_BASE_URL}/api/identity/verify/nin"
    headers = {
        "Authorization": f"Bearer {settings.YV_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "id": nin.strip(),
        "isSubjectConsent": True
    }
    response = requests.post(url, json=payload, headers=headers, timeout=15)
    response.raise_for_status()
    return response.json()


def face_match(official_photo: str, selfie: str):
    # ✅ CORRECT endpoint (includes /api)
    url = f"{settings.YV_BASE_URL}/api/biometrics/face-match"
    headers = {
        "Authorization": f"Bearer {settings.YV_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "image_one": official_photo,
        "image_two": selfie
    }
    response = requests.post(url, json=payload, headers=headers, timeout=15)
    response.raise_for_status()
    return response.json()