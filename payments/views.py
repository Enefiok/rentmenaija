import uuid
import requests
from django.conf import settings
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from hotels.models import RoomType, HotelBooking
import logging

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    logger.info("🔥 INITIATE_PAYMENT CALLED")
    logger.info(f"RequestMethod: {request.method}")
    logger.info(f"RequestPath: {request.path}")
    logger.info(f"User: {request.user.email}")
    logger.info(f"RawData: {request.data}")

    try:
        data = request.data  # DRF auto-parses JSON

        room_id = data.get('room_id')
        check_in_str = data.get('check_in')
        check_out_str = data.get('check_out')

        if not all([room_id, check_in_str, check_out_str]):
            missing = [k for k in ['room_id', 'check_in', 'check_out'] if not data.get(k)]
            logger.error(f"❌ Missing fields: {missing}")
            return Response(
                {'error': 'Missing required fields', 'missing': missing},
                status=status.HTTP_400_BAD_REQUEST
            )

        check_in = parse_date(check_in_str)
        check_out = parse_date(check_out_str)
        if not check_in or not check_out or check_out <= check_in:
            logger.error("❌ Invalid dates")
            return Response(
                {'error': 'Invalid check-in or check-out date'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            room = RoomType.objects.get(id=room_id)
            logger.info(f"✅ Room found: {room.name}, price={room.price_per_night}")
        except RoomType.DoesNotExist:
            logger.error(f"❌ Room ID {room_id} not found in DB")
            return Response(
                {'error': 'Room not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        nights = (check_out - check_in).days
        total_amount = room.price_per_night * nights
        logger.info(f"📅 Nights: {nights}, Total: ₦{total_amount}")

        transaction_ref = f"RMN_{uuid.uuid4().hex[:12].upper()}"
        user = request.user
        guest_full_name = f"{user.first_name} {user.last_name}".strip() or user.email
        guest_email = user.email
        guest_phone = getattr(user, 'phone', '')

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

        # Validate Squad config
        if not all([
            settings.SQUAD_SECRET_KEY,
            settings.SQUAD_BASE_URL,
            settings.SQUAD_PAYMENT_SUCCESS_URL
        ]):
            logger.error("❌ Missing SQUAD configuration in settings")
            booking.delete()
            return Response(
                {'error': 'Payment gateway not configured'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        amount_kobo = int(total_amount * 100)
        squad_payload = {
            "amount": str(amount_kobo),
            "email": guest_email,
            "currency": "NGN",
            "initiate_type": "inline",
            "transaction_ref": transaction_ref,
            "callback_url": settings.SQUAD_PAYMENT_SUCCESS_URL.strip(),
            "customer_name": guest_full_name,
            "payment_channels": ["card", "bank", "ussd", "transfer"],
            "metadata": {
                "booking_id": booking.id,
                "room_id": room.id,
                "hotel_id": room.hotel.id
            }
        }

        headers = {
            "Authorization": f"Bearer {settings.SQUAD_SECRET_KEY}",
            "Content-Type": "application/json"
        }

        logger.info("📤 Calling Squad API...")
        resp = requests.post(
            f"{settings.SQUAD_BASE_URL.strip()}/transaction/initiate",
            json=squad_payload,
            headers=headers,
            timeout=10
        )

        result = resp.json()
        logger.info(f"Squad Response: {resp.status_code} | {result}")

        if resp.status_code == 200 and result.get('status') == 200:
            checkout_url = result['data']['checkout_url'].strip()
            logger.info(f"✅ Success! Checkout URL: {checkout_url}")
            return Response({
                "checkout_url": checkout_url,
                "booking_id": booking.id
            })
        else:
            booking.delete()
            msg = result.get('message', 'Payment initiation failed')
            logger.error(f"❌ Squad failed: {msg}")
            return Response(
                {"error": msg},
                status=status.HTTP_400_BAD_REQUEST
            )

    except Exception as e:
        logger.exception("💥 UNEXPECTED ERROR in initiate_payment")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# Webhook remains unchanged (it's public, no auth needed)
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json

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