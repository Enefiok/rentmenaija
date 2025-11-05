import json
import uuid
import requests
from decimal import Decimal
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_date
from hotels.models import RoomType, HotelBooking

@csrf_exempt
def initiate_payment(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Use POST'}, status=405)

    try:
        # Handle JSON decode errors explicitly
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            return JsonResponse({'error': f'Invalid JSON: {str(e)}'}, status=400)

        room_id = data.get('room_id')
        check_in_str = data.get('check_in')      # "YYYY-MM-DD"
        check_out_str = data.get('check_out')
        guest_full_name = data.get('guest_full_name')
        guest_email = data.get('guest_email')
        guest_phone = data.get('guest_phone', '')
        
        # Validate required fields
        if not all([room_id, check_in_str, check_out_str, guest_full_name, guest_email]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        # Parse and validate dates
        check_in = parse_date(check_in_str)
        check_out = parse_date(check_out_str)
        if not check_in or not check_out or check_out <= check_in:
            return JsonResponse({'error': 'Invalid check-in or check-out date'}, status=400)

        # Fetch the room
        try:
            room = RoomType.objects.get(id=room_id)
        except RoomType.DoesNotExist:
            return JsonResponse({'error': 'Room not found'}, status=404)

        # Calculate total amount
        nights = (check_out - check_in).days
        total_amount = room.price_per_night * nights

        # Generate unique transaction reference
        transaction_ref = f"RMN_{uuid.uuid4().hex[:12].upper()}"

        # Get authenticated user (if any)
        user = request.user if request.user.is_authenticated else None

        # Create pending booking
        booking = HotelBooking.objects.create(
            user=user,
            room=room,
            check_in=check_in,
            check_out=check_out,
            num_guests=1,
            amount_paid_ngn=total_amount,
            status='pending',
            transaction_ref=transaction_ref,
            guest_full_name=guest_full_name,
            guest_email=guest_email,
            guest_phone=guest_phone
        )

        # Prepare Squad payload
        amount_kobo = int(total_amount * 100)

        squad_payload = {
            "amount": str(amount_kobo),
            "email": guest_email,
            "currency": "NGN",
            "initiate_type": "inline",
            "transaction_ref": transaction_ref,
            "callback_url": "https://rentmenaija-a4ed.onrender.com/payment-success/",  # ✅ NO TRAILING SPACES
            "customer_name": guest_full_name,
            "payment_channels": ["card", "bank", "ussd", "transfer"],
            "metadata": {
                "booking_id": booking.id,
                "room_id": room.id,
                "hotel_id": room.hotel.id
            }
        }

        headers = {
            "Authorization": "Bearer sandbox_sk_94f2b798466408ef4d19e848ee1a4d1a3e93f104046f",
            "Content-Type": "application/json"
        }

        # Call Squad API
        resp = requests.post(
            "https://sandbox-api-d.squadco.com/transaction/initiate",  # ✅ NO TRAILING SPACES
            json=squad_payload,
            headers=headers,
            timeout=10
        )

        result = resp.json()

        if resp.status_code == 200 and result.get('status') == 200:
            return JsonResponse({
                "checkout_url": result['data']['checkout_url'],
                "booking_id": booking.id
            })
        else:
            booking.delete()  # rollback on failure
            return JsonResponse({
                "error": result.get('message', 'Payment initiation failed')
            }, status=400)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def squad_webhook(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'ignored'}, status=200)

    try:
        payload = json.loads(request.body)

        if payload.get('Event') == 'charge_successful':
            body = payload.get('Body', {})
            if body.get('transaction_status') == 'Success':
                transaction_ref = body.get('transaction_ref')

                try:
                    booking = HotelBooking.objects.get(transaction_ref=transaction_ref)
                    booking.status = 'paid'
                    booking.save()
                    print(f"✅ Booking #{booking.id} marked as PAID")
                    return JsonResponse({'status': 'ok'})
                except HotelBooking.DoesNotExist:
                    print(f"⚠️ Webhook: Booking not found for {transaction_ref}")
                    return JsonResponse({'status': 'ignored'}, status=200)

        return JsonResponse({'status': 'ignored'}, status=200)

    except Exception as e:
        print("❌ Webhook error:", str(e))
        return JsonResponse({'error': 'Bad request'}, status=400)