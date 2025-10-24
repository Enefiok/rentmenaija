# listings/utils.py

import requests
from django.conf import settings

def reverse_geocode(lat, lng):
    """
    Returns {'city': ..., 'state': ...} from latitude and longitude.
    Uses OpenCage (if API key is set), otherwise falls back to Nominatim (free).
    Safe for Nigerian addresses.
    """
    # === 1. Try OpenCage (recommended for Nigeria) ===
    opencage_key = getattr(settings, 'OPENCAGE_API_KEY', None)
    if opencage_key:
        try:
            url = f"https://api.opencagedata.com/geocode/v1/json?q={lat}+{lng}&key={opencage_key}&countrycode=ng&language=en"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('results'):
                    comp = data['results'][0]['components']
                    # Extract city (prioritize city > town > village)
                    city = comp.get('city') or comp.get('town') or comp.get('village')
                    # Extract state
                    state = comp.get('state') or comp.get('region')
                    return {'city': city, 'state': state}
        except Exception as e:
            print(f"[OpenCage] Reverse geocoding failed: {e}")

    # === 2. Fallback: Nominatim (free, no API key needed) ===
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&countrycodes=ng&accept-language=en"
        response = requests.get(
            url,
            headers={'User-Agent': 'RentMeNaija'},  # Required by Nominatim
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            addr = data.get('address', {})
            city = addr.get('city') or addr.get('town') or addr.get('village')
            state = addr.get('state')
            return {'city': city, 'state': state}
    except Exception as e:
        print(f"[Nominatim] Reverse geocoding failed: {e}")

    # If both fail, return None values
    return {'city': None, 'state': None}