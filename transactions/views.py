# transactions/views.py

import uuid
import requests
import logging
from django.shortcuts import get_object_or_404 # ✅ ADDED: Import for release_funds
from django.conf import settings
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import timedelta

from .models import LeasePayment, Booking # Import the new model from *this* app
from listings.models import PropertyDraft, Property # Import Landlord Listing models (draft and published)
from agent_listings.models import AgentPropertyDraft, AgentProperty # Import Agent Listing models (draft and published)

logger = logging.getLogger(__name__)

# --- Helper function to get landlord/agent user ---
def get_landlord_or_agent_user(listing_type, listing_id):
    """Helper to find the user associated with the listing draft (landlord or agent)."""
    if listing_type == 'landlord_listing':
        try:
            listing_draft = PropertyDraft.objects.get(id=listing_id)
            # The user who created the landlord listing draft is the landlord
            return listing_draft.user
        except PropertyDraft.DoesNotExist:
            raise ValueError("Landlord Listing Draft not found")
    elif listing_type == 'agent_listing':
        try:
            agent_listing_draft = AgentPropertyDraft.objects.get(id=listing_id)
            # The agent who created the agent listing draft
            return agent_listing_draft.agent
        except AgentPropertyDraft.DoesNotExist:
            raise ValueError("Agent Listing Draft not found")
    else:
        raise ValueError("Invalid listing type")


@api_view(['POST'])
@permission_classes([IsAuthenticated]) # Require login for lease payments
def initiate_lease_payment(request):
    """
    Initiate a payment for a landlord or agent listing (e.g., security deposit, first month rent).
    Requires: listing_type ('landlord_listing' or 'agent_listing'), listing_id, payment_type.
    Uses authenticated user as the tenant.
    """
    logger.info("🔥 INITIATE_LEASE_PAYMENT CALLED")
    logger.info(f"User: {request.user.email}, Data: {request.data}")

    data = request.data
    listing_type = data.get('listing_type')
    listing_id = data.get('listing_id')
    payment_type = data.get('payment_type')

    if not all([listing_type, listing_id, payment_type]):
        missing = [k for k in ['listing_type', 'listing_id', 'payment_type'] if not data.get(k)]
        logger.error(f"❌ Missing fields: {missing}")
        return Response(
            {'error': 'Missing required fields', 'missing': missing},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Validate listing_type
    if listing_type not in ['landlord_listing', 'agent_listing', 'hotel_listing']:
        logger.error(f"❌ Invalid listing_type: {listing_type}")
        return Response(
            {"error": "Invalid listing_type. Must be 'landlord_listing', 'agent_listing', or 'hotel_listing'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Validate payment_type
    VALID_PAYMENT_TYPES = [
        'security_deposit', 'first_month_rent', 'last_month_rent', 'booking_fee'
    ]
    if payment_type not in VALID_PAYMENT_TYPES:
         logger.error(f"❌ Invalid payment_type: {payment_type}")
         return Response(
             {"error": f"Invalid payment_type. Must be one of: {VALID_PAYMENT_TYPES}."},
             status=status.HTTP_400_BAD_REQUEST
         )

    # Get the listing object to validate it exists and get details (like rent for calculation)
    try:
        if listing_type == 'landlord_listing':
            listing_obj = PropertyDraft.objects.get(id=listing_id) # Query PropertyDraft
            # Example: Calculate amount based on payment type and listing rent
            if payment_type == 'security_deposit':
                 # Example: Deposit is 1 month's rent, adjust logic as needed
                 amount = float(listing_obj.monthly_rent) # Ensure it's a float for Squad
            elif payment_type == 'first_month_rent':
                 amount = float(listing_obj.monthly_rent)
            elif payment_type == 'booking_fee':
                 # Example: Fixed booking fee, get from settings or listing detail if variable
                 amount = 10000.00 # Example fixed amount
            else:
                 # Handle other types or require amount from frontend if not derivable
                 logger.error(f"❌ Amount calculation not defined for payment_type: {payment_type}")
                 return Response(
                     {"error": f"Amount calculation not supported for {payment_type}"},
                     status=status.HTTP_400_BAD_REQUEST
                 )

        elif listing_type == 'agent_listing':
            listing_obj = AgentPropertyDraft.objects.get(id=listing_id) # Query AgentPropertyDraft
            # Similar logic for agent listing
            if payment_type == 'security_deposit':
                 amount = float(listing_obj.monthly_rent)
            elif payment_type == 'first_month_rent':
                 amount = float(listing_obj.monthly_rent)
            elif payment_type == 'booking_fee':
                 amount = 10000.00 # Example
            else:
                 logger.error(f"❌ Amount calculation not defined for payment_type: {payment_type}")
                 return Response(
                     {"error": f"Amount calculation not supported for {payment_type}"},
                     status=status.HTTP_400_BAD_REQUEST
                 )
        elif listing_type == 'hotel_listing':
            from hotels.models import HotelListing
            listing_obj = HotelListing.objects.get(id=listing_id)
            # Calculate amount for hotel stay (nightly rate * number of nights)
            check_in = data.get('check_in_date')
            check_out = data.get('check_out_date')
            
            if not check_in or not check_out:
                return Response(
                    {"error": "Check-in and check-out dates are required for hotel bookings."},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            # Calculate number of nights
            from datetime import datetime
            check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
            check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()
            nights = (check_out_date - check_in_date).days
            amount = float(listing_obj.price_per_night) * nights

    except (PropertyDraft.DoesNotExist, AgentPropertyDraft.DoesNotExist, HotelListing.DoesNotExist): # Catch specific DoesNotExist
        logger.error(f"❌ {listing_type.replace('_', ' ').title()} ID {listing_id} not found in DB")
        return Response(
            {"error": f"{listing_type.replace('_', ' ').title()} not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    # Determine the landlord/agent user for the payment record
    try:
        if listing_type in ['landlord_listing', 'agent_listing']:
            landlord_or_agent_user = get_landlord_or_agent_user(listing_type, listing_id)
        else:  # hotel_listing
            from hotels.models import HotelListing
            hotel_listing = HotelListing.objects.get(id=listing_id)
            # Assuming hotel owner is stored in the hotel listing model
            # Adjust this based on your actual hotel model structure
            landlord_or_agent_user = hotel_listing.owner  # or whatever field stores the owner
    except ValueError as e:
        logger.error(f"❌ Error getting landlord/agent user: {e}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except (PropertyDraft.DoesNotExist, AgentPropertyDraft.DoesNotExist, HotelListing.DoesNotExist): # Should not happen if the listing check above passed, but good practice
         logger.error(f"❌ Landlord/Agent user lookup failed for {listing_type} ID {listing_id}")
         return Response(
             {"error": f"{listing_type.replace('_', ' ').title()} owner not found."},
             status=status.HTTP_404_NOT_FOUND
         )

    # Generate unique transaction reference
    transaction_ref = f"LEASEPAY_{uuid.uuid4().hex[:12].upper()}"

    # Create the LeasePayment record in the database (status: pending)
    lease_payment = LeasePayment.objects.create(
        listing_type=listing_type,
        listing_id=listing_id,
        tenant=request.user, # The authenticated user is the tenant
        landlord_or_agent=landlord_or_agent_user,
        amount_paid_ngn=amount,
        payment_type=payment_type,
        status='pending',
        transaction_ref=transaction_ref
    )
    logger.info(f"✅ LeasePayment created: ID={lease_payment.id}, Ref={transaction_ref}, Amount={amount}")

    # --- NEW: Link to existing Booking if it exists and update status ---
    try:
        # Find the saved booking for this listing and user
        original_booking = Booking.objects.get(
            user=request.user,
            listing_type=listing_type,
            listing_id=listing_id,
            status='saved' # Only link to the 'saved' one
        )
        # Link the LeasePayment to the Booking
        original_booking.lease_payment = lease_payment
        original_booking.status = 'paid_pending_confirmation' # Update status immediately upon payment initiation
        original_booking.initial_amount_paid_ngn = amount
        original_booking.payment_type = payment_type
        if listing_type == 'hotel_listing':
            original_booking.check_in_date = data.get('check_in_date')
            original_booking.check_out_date = data.get('check_out_date')
        original_booking.save()
        lease_payment.booking = original_booking # Ensure the reverse link is also set
        lease_payment.save() # Save the lease_payment with the booking link
        logger.info(f"🔗 Lease Payment #{lease_payment.id} linked to Booking #{original_booking.id}, Booking status updated to 'paid_pending_confirmation'.")
    except Booking.DoesNotExist:
        # If no saved booking exists, create a booking record for this payment
        booking = Booking.objects.create(
            user=request.user,
            listing_type=listing_type,
            listing_id=listing_id,
            lease_payment=lease_payment,
            status='paid_pending_confirmation',
            initial_amount_paid_ngn=amount,
            payment_type=payment_type,
            check_in_date=data.get('check_in_date') if listing_type == 'hotel_listing' else None,
            check_out_date=data.get('check_out_date') if listing_type == 'hotel_listing' else None,
        )
        logger.info(f"📝 New Booking created for standalone payment: ID={booking.id}")
    except Booking.MultipleObjectsReturned:
        logger.error(f"❌ Multiple saved Bookings found for user {request.user.id}, {listing_type} ID {listing_id}. Cannot link LeasePayment #{lease_payment.id}.")
    # --- END NEW ---

    # --- Call Squad API ---
    if not all([
        settings.SQUAD_SECRET_KEY,
        settings.SQUAD_BASE_URL,
        settings.SQUAD_PAYMENT_SUCCESS_URL # Ensure this is set
    ]):
        logger.error("❌ Missing SQUAD configuration in settings")
        lease_payment.delete() # Clean up the pending record
        return Response(
            {'error': 'Payment gateway not configured'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    amount_kobo = int(amount * 100) # Convert Naira to Kobo
    squad_payload = {
        "amount": str(amount_kobo),
        "email": request.user.email,
        "currency": "NGN",
        "initiate_type": "inline", # Or "redirect" based on your preference
        "transaction_ref": transaction_ref,
        "callback_url": settings.SQUAD_PAYMENT_SUCCESS_URL.strip(), # Your success page URL
        "customer_name": f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email,
        "payment_channels": ["card", "bank", "ussd", "transfer"], # Adjust as needed
        "metadata": {
            "lease_payment_id": lease_payment.id, # Link back to our record
            "listing_type": listing_type,
            "listing_id": listing_id
        }
    }

    headers = {
        "Authorization": f"Bearer {settings.SQUAD_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    logger.info(f"📤 Calling Squad API for LeasePayment {lease_payment.id}...")
    try:
        resp = requests.post(
            f"{settings.SQUAD_BASE_URL.strip()}/transaction/initiate",
            json=squad_payload,
            headers=headers,
            timeout=10
        )

        result = resp.json()
        logger.info(f"Squad Response Status: {resp.status_code}, Data: {result}")

        if resp.status_code == 200 and result.get('status') == 200:
            checkout_url = result['data']['checkout_url'].strip()
            logger.info(f"✅ Success! Checkout URL: {checkout_url}")
            return Response({
                "checkout_url": checkout_url,
                "lease_payment_id": lease_payment.id
            })
        else:
            # Handle Squad error response
            lease_payment.status = 'failed' # Mark the payment attempt as failed
            lease_payment.save()
            msg = result.get('message', 'Squad payment initiation failed.')
            logger.error(f"❌ Squad failed: {msg}")
            return Response(
                {"error": msg},
                status=status.HTTP_400_BAD_REQUEST
            )

    except requests.exceptions.RequestException as e:
        # Handle network errors or Squad API being down
        logger.exception(f"💥 Error calling Squad API for LeasePayment {lease_payment.id}")
        lease_payment.status = 'failed' # Mark as failed due to external error
        lease_payment.save()
        return Response(
            {"error": f"Error initiating payment with Squad: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except Exception as e:
        # Handle other errors (e.g., JSON parsing)
        logger.exception(f"💥 Unexpected error during Squad call for LeasePayment {lease_payment.id}")
        lease_payment.status = 'failed'
        lease_payment.save()
        return Response(
            {"error": f"An unexpected error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# --- Updated Booking Views for Escrow System ---

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_booking(request):
    """
    Save a property to the user's bookings (like adding to cart).
    Requires: listing_type ('landlord_listing', 'agent_listing', or 'hotel_listing'), listing_id.
    """
    logger.info("🔥 SAVE_BOOKING CALLED")
    logger.info(f"User: {request.user.email}, Data: {request.data}")

    data = request.data
    listing_type = data.get('listing_type')
    listing_id = data.get('listing_id')
    check_in_date = data.get('check_in_date')  # For hotels
    check_out_date = data.get('check_out_date')  # For hotels

    if not all([listing_type, listing_id]):
        missing = [k for k in ['listing_type', 'listing_id'] if not data.get(k)]
        logger.error(f"❌ Missing fields: {missing}")
        return Response(
            {'error': 'Missing required fields', 'missing': missing},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Validate listing_type
    VALID_LISTING_TYPES = ['landlord_listing', 'agent_listing', 'hotel_listing']
    if listing_type not in VALID_LISTING_TYPES:
        logger.error(f"❌ Invalid listing_type: {listing_type}")
        return Response(
            {"error": f"Invalid listing_type. Must be one of: {VALID_LISTING_TYPES}."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Validate that the listing exists (check published listings)
    listing_exists = False
    try:
        if listing_type == 'landlord_listing':
            # Check if the ID corresponds to a published Property
            Property.objects.get(id=listing_id)
            listing_exists = True
        elif listing_type == 'agent_listing':
            # Check if the ID corresponds to a published AgentProperty
            AgentProperty.objects.get(id=listing_id)
            listing_exists = True
        elif listing_type == 'hotel_listing':
            # Check if the ID corresponds to a published HotelListing
            from hotels.models import HotelListing # Import here to avoid circular imports if necessary
            HotelListing.objects.get(id=listing_id)
            listing_exists = True
    except (Property.DoesNotExist, AgentProperty.DoesNotExist, HotelListing.DoesNotExist):
        logger.error(f"❌ Published {listing_type.replace('_', ' ').title()} ID {listing_id} not found in DB")
        return Response(
            {"error": f"Published {listing_type.replace('_', ' ').title()} not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if not listing_exists:
        logger.error(f"❌ Published {listing_type.replace('_', ' ').title()} ID {listing_id} not found in DB")
        return Response(
            {"error": f"Published {listing_type.replace('_', ' ').title()} not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    # Check if the user already has this property saved
    existing_booking = Booking.objects.filter(
        user=request.user,
        listing_type=listing_type,
        listing_id=listing_id,
        status__in=['saved', 'paid_pending_confirmation'] # Don't allow saving if already confirmed/cancelled for this property
    ).first()

    if existing_booking:
        logger.warning(f"⚠️ User {request.user.email} already has {listing_type} ID {listing_id} in bookings with status {existing_booking.status}")
        return Response(
            {"error": f"You have already saved this {listing_type.replace('_', ' ')}."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Create the new booking record
    booking_data = {
        'user': request.user,
        'listing_type': listing_type,
        'listing_id': listing_id,
        'status': 'saved' # Default status is saved
    }
    
    if listing_type == 'hotel_listing':
        booking_data['check_in_date'] = check_in_date
        booking_data['check_out_date'] = check_out_date

    booking = Booking.objects.create(**booking_data)
    logger.info(f"✅ Booking created: ID={booking.id}, User={request.user.username}, Listing={listing_type} ID {listing_id}")

    return Response({
        "message": "✅ Property saved to your bookings.",
        "booking_id": booking.id,
        "status": booking.status,
        "created_at": booking.created_at
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_bookings(request):
    """
    Retrieve all bookings for the authenticated user.
    """
    logger.info("📚 GET_BOOKINGS CALLED")
    logger.info(f"User: {request.user.email}")

    bookings = Booking.objects.filter(user=request.user).order_by('-created_at')

    # Prepare response data, potentially fetching related listing details
    booking_data = []
    for booking in bookings:
        item_data = {
            "id": booking.id,
            "property_title": booking.property_title, # Use the helper property
            "property_id": booking.listing_id,
            "listing_type": booking.listing_type,
            "status": booking.status,
            "created_at": booking.created_at,
            "is_in_cancellation_window": booking.is_in_cancellation_window,
            "is_in_confirmation_window": booking.is_in_confirmation_window,
            "initial_amount_paid_ngn": str(booking.initial_amount_paid_ngn) if booking.initial_amount_paid_ngn else None,
            "payment_type": booking.payment_type,
            "refund_status": booking.refund_status,
            "release_status": booking.release_status,
            "check_in_date": booking.check_in_date,
            "check_out_date": booking.check_out_date,
        }
        # If the booking has a payment, include payment details
        if booking.lease_payment:
            item_data.update({
                "lease_payment_id": booking.lease_payment.id,
                "payment_status": booking.lease_payment.status,
            })
        booking_data.append(item_data)

    return Response(booking_data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirm_booking(request, booking_id):
    """
    Confirm a booking that has been paid for.
    Requires: booking_id in the URL path.
    """
    logger.info(f"✅ CONFIRM_BOOKING CALLED for Booking ID: {booking_id}")
    logger.info(f"User: {request.user.email}")

    try:
        booking = Booking.objects.get(id=booking_id, user=request.user) # Ensure user owns the booking
    except Booking.DoesNotExist:
        logger.error(f"❌ Booking ID {booking_id} not found for user {request.user.email}")
        return Response(
            {"error": "Booking not found or you don't have permission to access it."},
            status=status.HTTP_404_NOT_FOUND
        )

    # Check if the booking can be confirmed (must be paid but not yet confirmed/cancelled)
    if booking.status != 'paid_pending_confirmation':
        logger.error(f"❌ Booking ID {booking_id} cannot be confirmed. Current status: {booking.status}")
        return Response(
            {"error": f"Cannot confirm booking with status '{booking.status}'. It must be 'paid_pending_confirmation'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Check if still in confirmation window
    if not booking.is_in_confirmation_window:
        logger.error(f"❌ Booking ID {booking_id} confirmation window has expired")
        return Response(
            {"error": "Confirmation window has expired."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Perform the confirmation logic
    booking.status = 'confirmed'
    booking.save()
    logger.info(f"✅ Booking ID {booking_id} confirmed for user {request.user.email}")

    # ✅ NEW: Trigger fund release logic here if conditions are met
    if booking.can_release_funds():
        # Attempt immediate release (or schedule a task if needed)
        try:
            # Get landlord details
            landlord_details = booking.get_landlord_account_details()
            if not landlord_details or not landlord_details['account_number']:
                logger.error(f"Cannot release funds for booking {booking.id}: Missing landlord bank details.")
                return Response({
                    "message": "✅ Your booking has been confirmed successfully.",
                    "booking_id": booking.id,
                    "status": booking.status,
                    "warning": "Funds cannot be released yet: Missing landlord bank details."
                }, status=status.HTTP_200_OK)

            # Get the correct bank code using the mapping
            bank_name_from_db = landlord_details['bank_name'].lower().strip()
            bank_code = settings.BANK_CODE_MAPPING.get(bank_name_from_db)

            if not bank_code:
                logger.error(f"Cannot release funds for booking {booking.id}: Bank code not configured for '{landlord_details['bank_name']}'")
                return Response({
                    "message": "✅ Your booking has been confirmed successfully.",
                    "booking_id": booking.id,
                    "status": booking.status,
                    "warning": f"Funds cannot be released yet: Bank code not configured for '{landlord_details['bank_name']}'"
                }, status=status.HTTP_200_OK)

            # Get your Squad merchant ID (from your dashboard)
            merchant_id = "SBQWA77KWD"  # Replace with your actual merchant ID from Squad dashboard

            # Create unique transaction reference with merchant ID
            transaction_ref = f"{merchant_id}_{booking.id}_{uuid.uuid4().hex[:8].upper()}"

            # Prepare disbursement data for Squad
            disbursement_data = {
                "transaction_reference": transaction_ref,
                "amount": str(int(booking.initial_amount_paid_ngn * 100)),  # Convert to kobo as string
                "bank_code": bank_code,
                "account_number": landlord_details['account_number'],
                "account_name": landlord_details['account_name'],  # This should match the name from account lookup
                "currency_id": "NGN",
                "remark": f"Payment for booking {booking.id} at {landlord_details['property_title']}"
            }

            headers = {
                "Authorization": f"Bearer {settings.SQUAD_SECRET_KEY}",
                "Content-Type": "application/json"
            }
            
            # Use the correct sandbox transfer endpoint
            squad_disburse_url = f"{settings.SQUAD_BASE_URL.strip()}/payout/transfer"

            response = requests.post(squad_disburse_url, json=disbursement_data, headers=headers, timeout=30)
            squad_response = response.json()

            if response.status_code == 200 and squad_response.get('success') is True:
                # Squad disbursement successful
                booking.mark_funds_released(payout_reference=squad_response.get('data', {}).get('transaction_reference'))
                logger.info(f"✅ Funds released for booking {booking.id} to {landlord_details['account_name']}.")
                return Response({
                    "message": "✅ Your booking has been confirmed successfully. Funds have been released.",
                    "booking_id": booking.id,
                    "status": booking.status,
                    "release_status": booking.release_status
                }, status=status.HTTP_200_OK)
            else:
                error_message = squad_response.get('message', 'Squad disbursement failed.')
                logger.error(f"❌ Squad disbursement failed for booking {booking.id}: {error_message}")
                # Optionally, update booking status to reflect disbursement failure
                # booking.release_status = 'failed'
                # booking.save()
                return Response({
                    "message": "✅ Your booking has been confirmed successfully.",
                    "booking_id": booking.id,
                    "status": booking.status,
                    "error": f"Funds release failed: {error_message}"
                }, status=status.HTTP_200_OK) # Or a different status if you want to signal partial success

        except requests.exceptions.RequestException as e:
            logger.exception(f"💥 Error calling Squad API for fund release for booking {booking.id}")
            return Response({
                "message": "✅ Your booking has been confirmed successfully.",
                "booking_id": booking.id,
                "status": booking.status,
                "error": f"Error releasing funds: {str(e)}"
            }, status=status.HTTP_200_OK) # Or a different status
        except Exception as e:
            logger.exception(f"💥 Unexpected error during fund release for booking {booking.id}")
            return Response({
                "message": "✅ Your booking has been confirmed successfully.",
                "booking_id": booking.id,
                "status": booking.status,
                "error": f"An unexpected error occurred releasing funds: {str(e)}"
            }, status=status.HTTP_200_OK) # Or a different status
    else:
        logger.info(f"Funds cannot be released yet for booking {booking.id} (conditions not met).")
        return Response({
            "message": "✅ Your booking has been confirmed successfully.",
            "booking_id": booking.id,
            "status": booking.status,
            "release_status": booking.release_status
        }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_booking(request, booking_id):
    """
    Cancel a booking (saved or paid).
    Requires: booking_id in the URL path.
    """
    logger.info(f"❌ CANCEL_BOOKING CALLED for Booking ID: {booking_id}")
    logger.info(f"User: {request.user.email}")

    try:
        booking = Booking.objects.get(id=booking_id, user=request.user) # Ensure user owns the booking
    except Booking.DoesNotExist:
        logger.error(f"❌ Booking ID {booking_id} not found for user {request.user.email}")
        return Response(
            {"error": "Booking not found or you don't have permission to access it."},
            status=status.HTTP_404_NOT_FOUND
        )

    # Check if the booking can be cancelled
    if booking.status in ['confirmed', 'cancelled', 'refunded', 'released']:
        logger.error(f"❌ Booking ID {booking_id} cannot be cancelled. Current status: {booking.status}")
        return Response(
            {"error": f"Cannot cancel booking with status '{booking.status}'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Check if still in cancellation window
    if not booking.is_in_cancellation_window:
        logger.error(f"❌ Booking ID {booking_id} cancellation window has expired")
        return Response(
            {"error": "Cancellation window has expired."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Perform the cancellation logic
    booking.status = 'cancelled'
    booking.refund_status = 'requested'
    booking.refund_processed_at = timezone.now()
    booking.save()
    logger.info(f"✅ Booking ID {booking_id} cancelled for user {request.user.email}")

    # TODO: Trigger refund logic here
    # trigger_refund(booking)

    return Response({
        "message": "🚫 Your booking has been cancelled successfully. Refund requested.",
        "booking_id": booking.id,
        "status": booking.status,
        "refund_status": booking.refund_status
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_refund(request, booking_id):
    """
    Request a refund for a paid booking (within cancellation window).
    Alternative endpoint to cancel_booking that explicitly handles refund.
    """
    logger.info(f"💰 REQUEST_REFUND CALLED for Booking ID: {booking_id}")
    logger.info(f"User: {request.user.email}")

    try:
        booking = Booking.objects.get(id=booking_id, user=request.user)
    except Booking.DoesNotExist:
        logger.error(f"❌ Booking ID {booking_id} not found for user {request.user.email}")
        return Response(
            {"error": "Booking not found or you don't have permission to access it."},
            status=status.HTTP_404_NOT_FOUND
        )

    # Check if eligible for refund
    if booking.status not in ['paid_pending_confirmation']:
        logger.error(f"❌ Booking ID {booking_id} not eligible for refund. Current status: {booking.status}")
        return Response(
            {"error": f"Cannot refund booking with status '{booking.status}'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Check if still in cancellation window
    if not booking.is_in_cancellation_window:
        logger.error(f"❌ Booking ID {booking_id} refund window has expired")
        return Response(
            {"error": "Refund window has expired."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Process refund request
    booking.status = 'cancelled'
    booking.refund_status = 'requested'
    booking.refund_processed_at = timezone.now()
    booking.save()
    logger.info(f"💰 Refund requested for booking ID {booking_id}")

    # TODO: Trigger actual refund process
    # trigger_refund(booking)

    return Response({
        "message": "💰 Refund requested successfully.",
        "booking_id": booking.id,
        "status": booking.status,
        "refund_status": booking.refund_status
    }, status=status.HTTP_200_OK)


# ✅ NEW: Fund Release View
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def release_funds(request, booking_id):
    """
    Release funds to the landlord/owner's account.
    This should be called manually by the landlord/owner or an admin after confirmation.
    """
    booking = get_object_or_404(Booking, id=booking_id)

    # ✅ UPDATED: Check if user is the landlord/owner of the listing associated with the booking
    # This assumes the booking's listing_id corresponds to a published listing (Property, AgentProperty, HotelListing)
    # and that we can get the owner from the published listing.
    listing_obj = booking.get_related_published_listing()
    if not listing_obj:
        logger.error(f"❌ Cannot release funds: Published listing for booking {booking.id} not found.")
        return Response({"error": "Associated listing not found."}, status=status.HTTP_404_NOT_FOUND)

    # Determine the owner based on the listing type
    owner_user = None
    if booking.listing_type == 'landlord_listing':
        # For landlord listings, the owner is the user linked to the PropertyDraft
        from listings.models import Property
        try:
            prop = Property.objects.select_related('draft').get(id=booking.listing_id)
            owner_user = prop.draft.user
        except Property.DoesNotExist:
            pass
    elif booking.listing_type == 'agent_listing':
        # For agent listings, the owner is the user linked to the AgentPropertyDraft
        from agent_listings.models import AgentProperty
        try:
            agent_prop = AgentProperty.objects.select_related('draft').get(id=booking.listing_id)
            owner_user = agent_prop.draft.agent
        except AgentProperty.DoesNotExist:
            pass
    elif booking.listing_type == 'hotel_listing':
        # For hotel listings, the owner is the 'owner' field on HotelListing
        from hotels.models import HotelListing
        try:
            hotel = HotelListing.objects.get(id=booking.listing_id)
            owner_user = hotel.owner
        except HotelListing.DoesNotExist:
            pass

    if not owner_user or request.user != owner_user:
        logger.error(f"❌ User {request.user.id} not authorized to release funds for booking {booking.id}. Owner is {getattr(owner_user, 'id', 'None')}.")
        return Response({"error": "Not authorized to release funds for this booking."}, status=status.HTTP_403_FORBIDDEN)

    # Check if release is possible
    if not booking.can_release_funds():
        reason = "Funds cannot be released because: "
        if booking.status != 'confirmed':
            reason += "Booking is not confirmed. "
        if booking.funds_released:
            reason += "Funds already released. "
        if booking.initial_amount_paid_ngn <= 0:
            reason += "No amount paid. "
        return Response({"error": reason.strip()}, status=status.HTTP_400_BAD_REQUEST)

    # Determine the listing type and get landlord/owner details
    # This assumes your listing models have the bank fields added earlier
    landlord_details = booking.get_landlord_account_details()
    if not landlord_details or not landlord_details['account_number']:
        return Response({"error": "Landlord/owner bank details not found or incomplete."}, status=status.HTTP_400_BAD_REQUEST)

    # Get the correct bank code using the mapping
    bank_name_from_db = landlord_details['bank_name'].lower().strip()
    bank_code = settings.BANK_CODE_MAPPING.get(bank_name_from_db)

    if not bank_code:
        return Response({
            "error": f"Bank code not configured for '{landlord_details['bank_name']}'. Cannot release funds."
        }, status=status.HTTP_400_BAD_REQUEST)

    # Get your Squad merchant ID (from your dashboard)
    merchant_id = "SBQWA77KWD"  # Replace with your actual merchant ID from Squad dashboard

    # Create unique transaction reference with merchant ID
    transaction_ref = f"{merchant_id}_{booking.id}_{uuid.uuid4().hex[:8].upper()}"

    # Prepare disbursement data for Squad
    disbursement_data = {
        "transaction_reference": transaction_ref,
        "amount": str(int(booking.initial_amount_paid_ngn * 100)),  # Convert to kobo as string
        "bank_code": bank_code,
        "account_number": landlord_details['account_number'],
        "account_name": landlord_details['account_name'],  # This should match the name from account lookup
        "currency_id": "NGN",
        "remark": f"Payment for booking {booking.id} at {landlord_details['property_title']}"
    }

    # Make the API call to Squad
    try:
        headers = {
            "Authorization": f"Bearer {settings.SQUAD_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        
        # Use the correct sandbox transfer endpoint
        squad_disburse_url = f"{settings.SQUAD_BASE_URL.strip()}/payout/transfer"

        response = requests.post(squad_disburse_url, json=disbursement_data, headers=headers, timeout=30)
        squad_response = response.json()

        if response.status_code == 200 and squad_response.get('success') is True:
            # Squad disbursement successful
            # Update your Booking record to reflect the release
            booking.mark_funds_released(payout_reference=squad_response.get('data', {}).get('transaction_reference')) # Use the reference from Squad if available

            return Response({
                "message": "Funds released successfully.",
                "squad_response": squad_response
            }, status=status.HTTP_200_OK)

        else:
            # Squad disbursement failed
            error_message = squad_response.get('message', 'Squad disbursement failed.')
            return Response({
                "error": f"Funds release failed: {error_message}",
                "squad_response": squad_response
            }, status=status.HTTP_400_BAD_REQUEST)

    except requests.exceptions.RequestException as e:
        # Network or connection error with Squad
        return Response({
            "error": f"Error connecting to payment gateway: {str(e)}"
        }, status=status.HTTP_502_BAD_GATEWAY)
    except Exception as e:
        # Other unexpected errors
        return Response({
            "error": f"An unexpected error occurred: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# You can add more views here later if needed, e.g., for retrieving lease payment status, etc.