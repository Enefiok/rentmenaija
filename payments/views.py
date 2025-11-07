import uuid
import requests
from django.conf import settings
from django.utils.dateparse import parse_date
from django.http import HttpResponse, JsonResponse
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
        data = request.data

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


# Updated webhook: returns JSON for POST, HTML for GET
from django.views.decorators.csrf import csrf_exempt
import json

@csrf_exempt
def squad_webhook(request):
    # 🔹 Handle GET redirect — show user-friendly HTML page
    if request.method == 'GET':
        transaction_ref = request.GET.get('reference')
        if transaction_ref:
            logger.info(f"🔗 GET redirect with reference: {transaction_ref}")

            # --- Check Hotel Bookings FIRST ---
            try:
                booking = HotelBooking.objects.get(transaction_ref=transaction_ref)
                if booking.status != 'paid':
                    booking.status = 'paid'
                    booking.save()
                    logger.info(f"✅ Hotel Booking #{booking.id} marked as PAID via GET")

                # ✅ Return HTML success page for Hotel Booking
                html = f"""
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Payment Successful - RentMeNaija</title>
                    <style>
                        body {{
                            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                            background: #f8f9fa;
                            margin: 0;
                            padding: 0;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            min-height: 100vh;
                            color: #333;
                        }}
                        .container {{
                            text-align: center;
                            background: white;
                            padding: 2.5rem;
                            border-radius: 12px;
                            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
                            max-width: 500px;
                            width: 90%;
                        }}
                        .success-icon {{
                            font-size: 3.5rem;
                            color: #28a745;
                            margin-bottom: 1rem;
                        }}
                        h1 {{
                            font-size: 1.8rem;
                            margin: 0 0 1rem;
                            color: #28a745;
                        }}
                        p {{
                            font-size: 1.1rem;
                            line-height: 1.6;
                            margin-bottom: 1.5rem;
                            color: #555;
                        }}
                        .booking-ref {{
                            background: #e9f7ef;
                            padding: 0.5rem;
                            border-radius: 6px;
                            font-family: monospace;
                            font-size: 0.95rem;
                            margin: 1rem 0;
                            display: inline-block;
                        }}
                        .btn {{
                            display: inline-block;
                            background: #007BFF;
                            color: white;
                            text-decoration: none;
                            padding: 0.8rem 1.5rem;
                            border-radius: 8px;
                            font-weight: 600;
                            margin-top: 1rem;
                            transition: background 0.2s;
                        }}
                        .btn:hover {{
                            background: #0069d9;
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="success-icon">✅</div>
                        <h1>Hotel Payment Successful!</h1>
                        <p>Your booking has been confirmed.</p>
                        <div class="booking-ref">Reference: {booking.transaction_ref}</div>
                        <p>We've sent a confirmation to your email.</p>
                        <a href="https://rentmenaija.com/my-bookings  " class="btn">View My Bookings</a>
                    </div>
                </body>
                </html>
                """
                return HttpResponse(html, content_type='text/html')

            # --- If not Hotel Booking, Check Lease Payment ---
            except HotelBooking.DoesNotExist:
                try:
                    # Import here to avoid potential circular import if transactions app isn't loaded yet
                    from transactions.models import LeasePayment
                    lease_payment = LeasePayment.objects.get(transaction_ref=transaction_ref)
                    if lease_payment.status != 'paid':
                        lease_payment.status = 'paid'
                        lease_payment.save()
                        logger.info(f"✅ Lease Payment #{lease_payment.id} marked as PAID via GET")

                        # --- NEW: Update associated Booking status ---
                        # Check if this LeasePayment is linked to a Booking
                        related_booking = getattr(lease_payment, 'booking', None) # Safely get the related booking via the OneToOneField
                        if related_booking and related_booking.status == 'saved':
                            related_booking.status = 'paid_pending_confirmation'
                            related_booking.save()
                            logger.info(f"✅ Booking #{related_booking.id} status updated to 'paid_pending_confirmation' via GET redirect.")
                        # --- END NEW ---

                    # ✅ Return HTML success page for Lease Payment
                    html = f"""
                    <!DOCTYPE html>
                    <html lang="en">
                    <head>
                        <meta charset="UTF-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        <title>Lease Payment Successful - RentMeNaija</title>
                        <style>
                            body {{
                                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                                background: #f8f9fa;
                                margin: 0;
                                padding: 0;
                                display: flex;
                                justify-content: center;
                                align-items: center;
                                min-height: 100vh;
                                color: #333;
                            }}
                            .container {{
                                text-align: center;
                                background: white;
                                padding: 2.5rem;
                                border-radius: 12px;
                                box-shadow: 0 4px 20px rgba(0,0,0,0.1);
                                max-width: 500px;
                                width: 90%;
                            }}
                            .success-icon {{
                                font-size: 3.5rem;
                                color: #28a745;
                                margin-bottom: 1rem;
                            }}
                            h1 {{
                                font-size: 1.8rem;
                                margin: 0 0 1rem;
                                color: #28a745;
                            }}
                            p {{
                                font-size: 1.1rem;
                                line-height: 1.6;
                                margin-bottom: 1.5rem;
                                color: #555;
                            }}
                            .payment-ref {{
                                background: #e9f7ef;
                                padding: 0.5rem;
                                border-radius: 6px;
                                font-family: monospace;
                                font-size: 0.95rem;
                                margin: 1rem 0;
                                display: inline-block;
                            }}
                            .btn {{
                                display: inline-block;
                                background: #007BFF;
                                color: white;
                                text-decoration: none;
                                padding: 0.8rem 1.5rem;
                                border-radius: 8px;
                                font-weight: 600;
                                margin-top: 1rem;
                                transition: background 0.2s;
                            }}
                            .btn:hover {{
                                background: #0069d9;
                            }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="success-icon">✅</div>
                            <h1>Lease Payment Successful!</h1>
                            <p>Your payment for the lease has been processed.</p>
                            <div class="payment-ref">Reference: {lease_payment.transaction_ref}</div>
                            <p>You will be contacted regarding the next steps.</p>
                            <a href="https://rentmenaija.com/my-payments  " class="btn">View My Payments</a> <!-- Adjust link as needed -->
                        </div>
                    </body>
                    </html>
                    """
                    return HttpResponse(html, content_type='text/html')

                # --- If neither Hotel Booking nor Lease Payment found ---
                except LeasePayment.DoesNotExist:
                    logger.warning(f"⚠️ GET redirect: Neither HotelBooking nor LeasePayment found for {transaction_ref}")
                    # ❌ Return generic HTML error page
                    html = """
                    <!DOCTYPE html>
                    <html lang="en">
                    <head>
                        <meta charset="UTF-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        <title>Payment Confirmation Failed - RentMeNaija</title>
                        <style>
                            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f8f9fa; }
                            .error { color: #dc3545; font-size: 2rem; margin-bottom: 1rem; }
                            p { font-size: 1.1rem; color: #555; }
                            a { display: inline-block; margin-top: 20px; padding: 10px 20px; background: #dc3545; color: white; text-decoration: none; border-radius: 5px; }
                        </style>
                    </head>
                    <body>
                        <div class="error">❌ Payment Confirmation Failed</div>
                        <p>We couldn't find your booking or payment record. Please contact support with your payment reference.</p>
                        <a href="https://rentmenaija.com  ">Go to Home</a>
                    </body>
                    </html>
                    """
                    return HttpResponse(html, content_type='text/html')

        # No reference — show error
        html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Invalid Request - RentMeNaija</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f8f9fa; }
                p { font-size: 1.1rem; color: #555; }
                a { display: inline-block; margin-top: 20px; padding: 10px 20px; background: #6c757d; color: white; text-decoration: none; border-radius: 5px; }
            </style>
        </head>
        <body>
            <p>Invalid payment confirmation request.</p>
            <a href="https://rentmenaija.com  ">Go to Home</a>
        </body>
        </html>
        """
        return HttpResponse(html, content_type='text/html')

    # 🔹 Handle POST webhook (JSON response for server-to-server)
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

                # --- Check Hotel Bookings FIRST ---
                try:
                    booking = HotelBooking.objects.get(transaction_ref=transaction_ref)
                    if booking.status != 'paid':
                        booking.status = 'paid'
                        booking.save()
                        logger.info(f"✅ Hotel Booking #{booking.id} marked as PAID via POST")
                    return JsonResponse({'status': 'ok'})
                # --- If not Hotel Booking, Check Lease Payment ---
                except HotelBooking.DoesNotExist:
                    try:
                        # Import here
                        from transactions.models import LeasePayment
                        lease_payment = LeasePayment.objects.get(transaction_ref=transaction_ref)
                        if lease_payment.status != 'paid':
                            lease_payment.status = 'paid'
                            lease_payment.save()
                            logger.info(f"✅ Lease Payment #{lease_payment.id} marked as PAID via POST")

                            # --- NEW: Update associated Booking status ---
                            # Check if this LeasePayment is linked to a Booking
                            related_booking = getattr(lease_payment, 'booking', None) # Safely get the related booking via the OneToOneField
                            if related_booking and related_booking.status == 'saved':
                                related_booking.status = 'paid_pending_confirmation'
                                related_booking.save()
                                logger.info(f"✅ Booking #{related_booking.id} status updated to 'paid_pending_confirmation' via POST webhook.")
                            # --- END NEW ---

                        return JsonResponse({'status': 'ok'})
                    # --- If neither found ---
                    except LeasePayment.DoesNotExist:
                        logger.warning(f"⚠️ Webhook: Neither HotelBooking nor LeasePayment found for {transaction_ref}")
                        # Squad might send webhook for a reference that doesn't exist in our DB (e.g., old, deleted records)
                        return JsonResponse({'status': 'ignored'}, status=200)

        return JsonResponse({'status': 'ignored'}, status=200)

    except Exception as e:
        logger.exception("❌ Webhook error")
        return JsonResponse({'error': 'Bad request'}, status=400)

# Note: The new 'initiate_lease_payment' view is now in the 'transactions' app's views.py