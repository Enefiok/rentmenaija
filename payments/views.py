import json
import uuid
import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_date
from hotels.models import RoomType, HotelBooking
import logging

logger = logging.getLogger(__name__)

@csrf_exempt
def initiate_payment(request):
    # Log entry
    logger.info("🔥 INITIATE_PAYMENT CALLED")
    logger.info(f"RequestMethod: {request.method}")
    logger.info(f"RequestPath: {request.path}")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"RawBody: {request.body}")

    if request.method != 'POST':
        logger.warning("⚠️ Non-POST request")
        return JsonResponse({'error': 'Use POST'}, status=405)

    try:
        # Check empty body
        if not request.body.strip():
            logger.error("❌ Empty request body")
            return JsonResponse({'error': 'Request body is empty'}, status=400)

        # Parse JSON
        try:
            data = json.loads(request.body)
            logger.info(f"✅ Parsed JSON: {data}")
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON decode failed: {str(e)} | Raw: {request.body}")
            return JsonResponse({'error': f'Invalid JSON: {str(e)}'}, status=400)

        # Extract fields
        room_id = data.get('room_id')
        check_in_str = data.get('check_in')
        check_out_str = data.get('check_out')
        guest_full_name = data.get('guest_full_name')
        guest_email = data.get('guest_email')
        guest_phone = data.get('guest_phone', '')

        logger.info(f"Fields: room_id={room_id}, check_in={check_in_str}, check_out={check_out_str}, email={guest_email}")

        # Validate required
        required = ['room_id', 'check_in', 'check_out', 'guest_full_name', 'guest_email']
        missing = [field for field in required if not data.get(field)]
        if missing:
            logger.error(f"❌ Missing fields: {missing}")
            return JsonResponse({'error': 'Missing required fields', 'missing': missing}, status=400)

        # Validate dates
        check_in = parse_date(check_in_str)
        check_out = parse_date(check_out_str)
        if not check_in or not check_out or check_out <= check_in:
            logger.error("❌ Invalid dates")
            return JsonResponse({'error': 'Invalid check-in or check-out date'}, status=400)

        # Fetch room
        try:
            room = RoomType.objects.get(id=room_id)
            logger.info(f"✅ Room found: {room.room_name}, price={room.price_per_night}")
        except RoomType.DoesNotExist:
            logger.error(f"❌ Room ID {room_id} not found in DB")
            return JsonResponse({'error': 'Room not found'}, status=404)

        # Calculate amount
        nights = (check_out - check_in).days
        total_amount = room.price_per_night * nights
        logger.info(f"📅 Nights: {nights}, Total: ₦{total_amount}")

        # Create booking
        transaction_ref = f"RMN_{uuid.uuid4().hex[:12].upper()}"
        user = request.user if request.user.is_authenticated else None
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
        logger.info(f"✅ Booking created: ID={booking.id}, Ref={transaction_ref}")

        # Squad payload — NO TRAILING SPACES
        amount_kobo = int(total_amount * 100)
        squad_payload = {
            "amount": str(amount_kobo),
            "email": guest_email,
            "currency": "NGN",
            "initiate_type": "inline",
            "transaction_ref": transaction_ref,
            "callback_url": "https://rentmenaija-a4ed.onrender.com/payment-success/",  # ✅ Clean
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

        logger.info("📤 Calling Squad API...")
        resp = requests.post(
            "https://sandbox-api-d.squadco.com/transaction/initiate",  # ✅ Clean
            json=squad_payload,
            headers=headers,
            timeout=10
        )

        result = resp.json()
        logger.info(f"Squad Response: {resp.status_code} | {result}")

        if resp.status_code == 200 and result.get('status') == 200:
            checkout_url = result['data']['checkout_url']
            logger.info(f"✅ Success! Checkout URL: {checkout_url}")
            return JsonResponse({
                "checkout_url": checkout_url,
                "booking_id": booking.id
            })
        else:
            booking.delete()
            msg = result.get('message', 'Payment initiation failed')
            logger.error(f"❌ Squad failed: {msg}")
            return JsonResponse({"error": msg}, status=400)

    except Exception as e:
        logger.exception("💥 UNEXPECTED ERROR in initiate_payment")
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def squad_webhook(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'ignored'}, status=200)

    try:
        payload = json.loads(request.body)
        logger.info(f"🔔 Webhook received: {payload.get('Event')}")

        if payload.get('Event') == 'charge_successful':
            body = payload.get('Body', {})
            if body.get('transaction_status') == 'Success':
                transaction_ref = body.get('transaction_ref')
                logger.info(f"🔗 Processing payment success: {transaction_ref}")

                try:
                    booking = HotelBooking.objects.get(transaction_ref=transaction_ref)
                    booking.status = 'paid'
                    booking.save()
                    logger.info(f"✅ Booking #{booking.id} marked as PAID")
                    return JsonResponse({'status': 'ok'})
                except HotelBooking.DoesNotExist:
                    logger.warning(f"⚠️ Webhook: Booking not found for {transaction_ref}")
                    return JsonResponse({'status': 'ignored'}, status=200)

        return JsonResponse({'status': 'ignored'}, status=200)

    except Exception as e:
        logger.exception("❌ Webhook error")
        return JsonResponse({'error': 'Bad request'}, status=400)