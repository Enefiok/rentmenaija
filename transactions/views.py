# transactions/views.py

import uuid
import requests
import logging
from django.shortcuts import get_object_or_404 # ✅ ADDED: Import for release_funds
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt # Add this import
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import timedelta

from .models import LeasePayment, Booking # Import the new model from *this* app
from listings.models import PropertyDraft, Property # Import Landlord Listing models (draft and published)
from agent_listings.models import AgentPropertyDraft, AgentProperty # Import Agent Listing models (draft and published)
from hotels.models import HotelListing 

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


# Apply @csrf_exempt to POST/PUT/DELETE views that use token auth
@api_view(['POST'])
@permission_classes([IsAuthenticated]) # Require login for lease payments
@csrf_exempt # Exempt from CSRF for token-authenticated API
def initiate_lease_payment(request):
    """
    Initiate a payment for a landlord or agent listing (e.g., security deposit, first month rent, full lease amount).
    For hotel listings, requires check_in_date, check_out_date, and room_type_id.
    Requires: listing_type ('landlord_listing', 'agent_listing', or 'hotel_listing'), listing_id, payment_type.
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

    # Validate payment_type - Include 'full_lease_payment'
    VALID_PAYMENT_TYPES = [
        'security_deposit', 'first_month_rent', 'last_month_rent', 'booking_fee', 'full_lease_payment'
    ]
    if payment_type not in VALID_PAYMENT_TYPES:
         logger.error(f"❌ Invalid payment_type: {payment_type}")
         return Response(
             {"error": f"Invalid payment_type. Must be one of: {VALID_PAYMENT_TYPES}."},
             status=status.HTTP_400_BAD_REQUEST
         )

    # Get the listing object to validate it exists and get details (like rent for calculation)
    # Prioritize published listings (Property, AgentProperty, HotelListing)
    listing_obj = None
    try:
        if listing_type == 'landlord_listing':
            # First, try to find the published Property
            try:
                listing_obj = Property.objects.get(id=listing_id)
                # If found, use the draft details for rent, term, etc.
                listing_obj_for_calculation = listing_obj.draft
            except Property.DoesNotExist:
                # If not found, fall back to the draft
                listing_obj_for_calculation = PropertyDraft.objects.get(id=listing_id)
                listing_obj = listing_obj_for_calculation # Assign draft as listing_obj if published not found
        elif listing_type == 'agent_listing':
            # First, try to find the published AgentProperty
            try:
                listing_obj = AgentProperty.objects.get(id=listing_id)
                # If found, use the draft details for rent, term, etc.
                listing_obj_for_calculation = listing_obj.draft
            except AgentProperty.DoesNotExist:
                # If not found, fall back to the draft
                listing_obj_for_calculation = AgentPropertyDraft.objects.get(id=listing_id)
                listing_obj = listing_obj_for_calculation # Assign draft as listing_obj if published not found
        elif listing_type == 'hotel_listing':
            # For hotels, assume HotelListing is the published version
            from hotels.models import HotelListing
            listing_obj = HotelListing.objects.get(id=listing_id)
            listing_obj_for_calculation = listing_obj # For hotels, the object itself is used for calculation

        # Example: Calculate amount based on payment type and listing rent
        if payment_type == 'security_deposit':
             # Example: Deposit is 1 month's rent, adjust logic as needed
             amount = float(listing_obj_for_calculation.monthly_rent) # Ensure it's a float for Squad
        elif payment_type == 'first_month_rent':
             amount = float(listing_obj_for_calculation.monthly_rent)
        elif payment_type == 'booking_fee':
             # Example: Fixed booking fee, get from settings or listing detail if variable
             amount = 10000.00 # Example fixed amount
        # --- NEW: Calculate full lease amount ---
        elif payment_type == 'full_lease_payment':
            lease_term = listing_obj_for_calculation.lease_term_preference # e.g., '1_year', '2_years', 'monthly', '6_months'
            monthly_rent = float(listing_obj_for_calculation.monthly_rent)

            # Define a mapping for lease terms to number of months
            lease_term_to_months = {
                'monthly': 1,
                '6_months': 6,
                '1_year': 12,
                '2_years': 24,
                # Add more if needed
            }

            # Calculate the number of months based on the lease term
            num_months = lease_term_to_months.get(lease_term)

            if num_months is None:
                logger.error(f"❌ Unsupported lease_term_preference for full payment: {lease_term}")
                return Response(
                    {"error": f"Full lease payment calculation not supported for lease term: {lease_term}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Calculate the total amount for the full lease term
            amount = monthly_rent * num_months
            logger.info(f"Calculated full lease amount: {amount} for {num_months} months (term: {lease_term})")
        # --- END NEW ---
        else:
             # Handle other types or require amount from frontend if not derivable
             logger.error(f"❌ Amount calculation not defined for payment_type: {payment_type}")
             return Response(
                 {"error": f"Amount calculation not supported for {payment_type}"},
                 status=status.HTTP_400_BAD_REQUEST
             )

        # Calculate amount for hotel stay (room type nightly rate * number of nights)
        if listing_type == 'hotel_listing':
            check_in = data.get('check_in_date')
            check_out = data.get('check_out_date')
            room_type_id = data.get('room_type_id') # Get the specific room type ID

            if not all([check_in, check_out, room_type_id]):
                missing = [k for k in ['check_in_date', 'check_out_date', 'room_type_id'] if not data.get(k)]
                logger.error(f"❌ Missing fields for hotel payment: {missing}")
                return Response(
                    {"error": f"Check-in date, check-out date, and room type ID are required for hotel bookings. Missing: {missing}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validate dates format and calculate nights
            try:
                from datetime import datetime
                check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
                check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()
                if check_out_date <= check_in_date:
                    return Response(
                        {"error": "Check-out date must be after check-in date."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                nights = (check_out_date - check_in_date).days
                if nights <= 0:
                    return Response(
                        {"error": "Number of nights must be greater than 0."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Get the specific RoomType associated with this HotelListing
            try:
                from hotels.models import RoomType
                room_type = RoomType.objects.get(id=room_type_id, hotel_id=listing_id) # Ensure the room belongs to the specified hotel
            except RoomType.DoesNotExist:
                logger.error(f"❌ RoomType ID {room_type_id} not found for HotelListing ID {listing_id}")
                return Response(
                    {"error": f"Room type ID {room_type_id} not found for the specified hotel."},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Calculate the amount using the room type's nightly rate
            amount = float(room_type.price_per_night) * nights
            logger.info(f"Calculated hotel amount: {amount} for {nights} nights in RoomType {room_type.name} (ID: {room_type.id})")

    except (Property.DoesNotExist, AgentProperty.DoesNotExist, HotelListing.DoesNotExist, PropertyDraft.DoesNotExist, AgentPropertyDraft.DoesNotExist): # Catch specific DoesNotExist
        logger.error(f"❌ {listing_type.replace('_', ' ').title()} ID {listing_id} not found in DB")
        return Response(
            {"error": f"{listing_type.replace('_', ' ').title()} not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    # Determine the landlord/agent user for the payment record
    # Use the listing_obj (which could be published or draft) to get the owner
    try:
        if listing_type in ['landlord_listing', 'agent_listing']:
            # Use the draft linked to the found listing_obj to get the user
            if hasattr(listing_obj, 'draft'):
                 landlord_or_agent_user = listing_obj.draft.user if listing_type == 'landlord_listing' else listing_obj.draft.agent
            else:
                 # Fallback if somehow listing_obj is the draft itself
                 landlord_or_agent_user = get_landlord_or_agent_user(listing_type, listing_id)
        else:  # hotel_listing
            from hotels.models import HotelListing
            hotel_listing = HotelListing.objects.get(id=listing_id) # Re-fetch to get owner safely
            # Assuming hotel owner is stored in the hotel listing model
            # Adjust this based on your actual hotel model structure
            landlord_or_agent_user = hotel_listing.owner  # or whatever field stores the owner
    except ValueError as e:
        logger.error(f"❌ Error getting landlord/agent user: {e}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except (Property.DoesNotExist, AgentProperty.DoesNotExist, HotelListing.DoesNotExist): # Should not happen if the listing check above passed, but good practice
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
            # Store the room type ID for hotel bookings (assuming your Booking model has this field)
            original_booking.room_type_id = data.get('room_type_id') # Update based on your Booking model
        original_booking.save()
        lease_payment.booking = original_booking # Ensure the reverse link is also set
        lease_payment.save() # Save the lease_payment with the booking link
        logger.info(f"🔗 Lease Payment #{lease_payment.id} linked to Booking #{original_booking.id}, Booking status updated to 'paid_pending_confirmation'.")
    except Booking.DoesNotExist:
        # If no saved booking exists, create a booking record for this payment
        booking_data = {
            'user': request.user,
            'listing_type': listing_type,
            'listing_id': listing_id,
            'lease_payment': lease_payment,
            'status': 'paid_pending_confirmation',
            'initial_amount_paid_ngn': amount,
            'payment_type': payment_type,
            'check_in_date': data.get('check_in_date') if listing_type == 'hotel_listing' else None,
            'check_out_date': data.get('check_out_date') if listing_type == 'hotel_listing' else None,
        }
        # Add room_type_id to the booking data if it's a hotel booking (assuming your Booking model has this field)
        if listing_type == 'hotel_listing':
            booking_data['room_type_id'] = data.get('room_type_id') # Update based on your Booking model
        booking = Booking.objects.create(**booking_data)
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


# Apply @csrf_exempt to POST/PUT/DELETE views that use token auth
@api_view(['POST'])
@csrf_exempt # Exempt from CSRF for token-authenticated API
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
            # Only store dates if provided; allow null for 'saved' status
        booking_data['check_in_date'] = check_in_date if check_in_date else None
        booking_data['check_out_date'] = check_out_date if check_out_date else None

    booking = Booking.objects.create(**booking_data)
    logger.info(f"✅ Booking created: ID={booking.id}, User={request.user.username}, Listing={listing_type} ID {listing_id}")

    return Response({
        "message": "✅ Property saved to your bookings.",
        "booking_id": booking.id,
        "status": booking.status,
        "created_at": booking.created_at
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@csrf_exempt
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
@csrf_exempt
def confirm_booking(request, booking_id):
    """
    Confirm a booking that has been paid for.
    Requires: booking_id in the URL path.
    The booking must be in 'paid_pending_confirmation' status and within the confirmation window.
    Upon confirmation, attempts to release funds to the landlord/agent.
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
        # Mark as expired/failed if necessary, though status might remain 'paid_pending_confirmation'
        # until a scheduled task processes it.
        return Response(
            {"error": "Confirmation window has expired. Automatic cancellation/refund may apply."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Store the previous status to check if it was 'paid_pending_confirmation'
    # Note: At this point, the booking object fetched hasn't been modified yet
    previous_status = booking.status

    if previous_status != 'paid_pending_confirmation':
        logger.error(f"❌ Booking ID {booking_id} cannot be confirmed. Current status: {previous_status}")
        return Response(
            {"error": f"Cannot confirm booking with status '{previous_status}'. It must be 'paid_pending_confirmation'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Perform the confirmation logic (update status)
    booking.status = 'confirmed'
    # booking.save() # Don't save yet, do release first if applicable

    # NEW: Check if fund release should happen *now* upon confirmation
    # Assuming the goal is to release funds immediately upon successful confirmation
    # and if the payment amount is greater than 0 and funds haven't been released yet.
    should_release_funds_now = (
        booking.initial_amount_paid_ngn > 0 and  # There is an amount to release
        not booking.funds_released and           # Funds have not been released yet
        booking.status == 'confirmed'            # The status is being set to confirmed
    )

    if should_release_funds_now:
        # Attempt immediate release (or schedule a task if needed)
        try:
            # Get landlord details
            landlord_details = booking.get_landlord_account_details()
            if not landlord_details or not landlord_details['account_number']:
                logger.error(f"Cannot release funds for booking {booking.id}: Missing landlord bank details.")
                # Save the confirmation status even if release fails initially
                booking.save()
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
                # Save the confirmation status even if release fails initially
                booking.save()
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
                message = "✅ Your booking has been confirmed successfully. Funds have been released."
            else:
                error_message = squad_response.get('message', 'Squad disbursement failed.')
                logger.error(f"❌ Squad disbursement failed for booking {booking.id}: {error_message}")
                # Keep release_status as 'pending' or set to 'failed', depending on your retry logic
                # The booking is still confirmed, but release failed.
                message = f"✅ Your booking has been confirmed successfully. Funds release failed: {error_message}"

        except requests.exceptions.RequestException as e:
            logger.exception(f"💥 Error calling Squad API for fund release for booking {booking.id}")
            # The booking is still confirmed, but release failed due to an API error.
            message = f"✅ Your booking has been confirmed successfully. Error releasing funds: {str(e)}"
        except Exception as e:
            logger.exception(f"💥 Unexpected error during fund release for booking {booking.id}")
            # The booking is still confirmed, but release failed due to an unexpected error.
            message = f"✅ Your booking has been confirmed successfully. An unexpected error occurred releasing funds: {str(e)}"
    else:
        # If conditions for immediate release aren't met upon confirmation
        # (e.g., no amount paid, or funds were already somehow marked as released before this call)
        logger.info(f"Funds will not be released now for booking {booking.id} (conditions not met for immediate release).")
        message = "✅ Your booking has been confirmed successfully."

    # Finally, save the booking status update (and any changes made during release attempts)
    booking.save()

    return Response({
        "message": message,
        "booking_id": booking.id,
        "status": booking.status,
        "release_status": booking.release_status
           }, status=status.HTTP_200_OK)
    


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@csrf_exempt
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
@csrf_exempt
def request_refund(request, booking_id):
    """
    Request a refund for a paid booking (e.g., 'paid_pending_confirmation' status).
    This could be used before confirmation window expires (if within cancellation window),
    or potentially after confirmation window expires if the automatic expiration
    hasn't been processed yet by the scheduled task, but before the landlord manually releases funds.
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
    # Refunds are primarily for 'paid_pending_confirmation' status.
    # Consider if 'confirmed' bookings (where release failed) might also be eligible,
    # depending on your policy. For now, restrict to 'paid_pending_confirmation'.
    if booking.status not in ['paid_pending_confirmation']:
        logger.error(f"❌ Booking ID {booking_id} not eligible for manual refund. Current status: {booking.status}")
        return Response(
            {"error": f"Cannot request manual refund for booking with status '{booking.status}'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Check if still in cancellation window (or perhaps confirmation window for 'paid_pending_confirmation'?)
    # If the idea is the user can *always* request a refund before confirmation (even if cancellation window passed),
    # or if the request happens *after* the automatic expiration but *before* the scheduled task runs,
    # this check might need adjustment or removal for 'paid_pending_confirmation'.
    # For now, keeping the cancellation window check for consistency unless a specific rule for 'paid_pending_confirmation' refunds is defined differently.
    # If the automatic expiration sets a specific refund status, that might be a better check.
    # Let's assume manual refund requests for 'paid_pending_confirmation' follow the cancellation window rule for now.
    if not booking.is_in_cancellation_window:
        logger.error(f"❌ Booking ID {booking_id} manual refund window has expired (based on cancellation window)")
        # Alternatively, if a booking is 'paid_pending_confirmation' but past its *confirmation* window,
        # the user might expect a manual refund request to still work, assuming the automatic system hasn't run yet.
        # You might need a specific check here if the confirmation window has passed but automatic cancellation hasn't occurred yet.
        # For example:
        # if booking.status == 'paid_pending_confirmation' and not booking.is_in_confirmation_window:
        #     # Allow refund request here if automatic cancellation hasn't happened yet
        #     pass # Or implement specific logic
        # else:
        #     return Response({"error": "Refund window has expired."}, status=status.HTTP_400_BAD_REQUEST)
        # For now, using the simpler cancellation window check.
        return Response(
            {"error": "Refund window has expired."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Check again if the confirmation window is still valid at the moment of this request,
    # because time might have passed since the initial checks or the request was made late.
    # This is crucial: if the window expired *after* the cancellation check but before this point,
    # the automatic process should handle it, not a manual request now.
    if booking.status == 'paid_pending_confirmation' and not booking.is_in_confirmation_window:
         logger.error(f"❌ Booking ID {booking_id} cannot have manual refund requested now: Confirmation window expired, automatic process should handle it.")
         return Response(
            {"error": "Confirmation window has expired. Automatic cancellation/refund process should handle this shortly."},
            status=status.HTTP_400_BAD_REQUEST
         )

    # Process refund request
    # It's safer to set a status like 'refund_requested_pending_confirmation_expiry'
    # if the booking is still 'paid_pending_confirmation' and within the cancellation/confirmation window,
    # and let the scheduled task handle the actual Squad refund call and final status update.
    # However, if you want to process it immediately here (assuming it's allowed):
    # Assuming the booking is still in 'paid_pending_confirmation' and within the applicable window
    booking.status = 'cancelled' # Or a new status like 'refund_requested_manual' if you want to distinguish
    booking.refund_status = 'requested'
    booking.refund_processed_at = timezone.now()
    booking.save()
    logger.info(f"💰 Manual refund requested for booking ID {booking_id}")

    # TODO: Trigger actual refund process (e.g., call Squad refund API)
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
@csrf_exempt
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
        "remark": f"Payment for booking {booking.id} at {booking.property_title}"
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