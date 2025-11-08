# transactions/models.py

from django.db import models
from django.conf import settings  # Use your custom user model
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

class LeasePayment(models.Model):
    """
    Model to represent payments for landlord/agent listings (e.g., security deposit, first month rent).
    """
    PAYMENT_TYPE_CHOICES = [
        ('security_deposit', 'Security Deposit'),
        ('first_month_rent', 'First Month Rent'),
        ('last_month_rent', 'Last Month Rent'),
        ('booking_fee', 'Booking Fee'),
        # Add other types as needed
    ]

    LISTING_TYPE_CHOICES = [
        ('landlord_listing', 'Landlord Listing'),
        ('agent_listing', 'Agent Listing'),
        ('hotel_listing', 'Hotel Listing'), # Added this line
    ]

    id = models.AutoField(primary_key=True)
    listing_type = models.CharField(max_length=20, choices=LISTING_TYPE_CHOICES)
    # Store the ID of the related listing draft (either PropertyDraft or AgentPropertyDraft)
    listing_id = models.IntegerField()

    # Links to the users involved
    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='lease_payments_initiated'
    )
    # This could be the landlord (for landlord_listing) or the agent (for agent_listing)
    # Note: This user is the one who *created* the listing draft (PropertyDraft.user or AgentPropertyDraft.agent)
    landlord_or_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='lease_payments_received'
    )

    amount_paid_ngn = models.DecimalField(max_digits=10, decimal_places=2) # Amount to be paid
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES) # e.g., security_deposit
    status = models.CharField(max_length=20, default='pending') # e.g., pending, paid, failed, refunded
    transaction_ref = models.CharField(max_length=100, unique=True) # Unique reference for Squad
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.payment_type} for {self.get_listing_type_display()} ID {self.listing_id} - Tenant: {self.tenant.username}, Amount: {self.amount_paid_ngn}"

    # Optional: Method to get the related listing object for logic
    def get_related_listing(self):
        if self.listing_type == 'landlord_listing':
            try:
                # Import here to avoid circular imports
                from listings.models import PropertyDraft # Or Property if linking to published property
                return PropertyDraft.objects.get(id=self.listing_id)
            except (ImportError, PropertyDraft.DoesNotExist):
                return None
        elif self.listing_type == 'agent_listing':
            try:
                # Import here to avoid circular imports
                from agent_listings.models import AgentPropertyDraft # Or AgentProperty if linking to published property
                return AgentPropertyDraft.objects.get(id=self.listing_id)
            except (ImportError, AgentPropertyDraft.DoesNotExist):
                return None
        elif self.listing_type == 'hotel_listing':
             try:
                 # Import here to avoid circular imports
                 from hotels.models import HotelListing # Link to the HotelListing model
                 return HotelListing.objects.get(id=self.listing_id)
             except (ImportError, HotelListing.DoesNotExist):
                 return None
        return None


# --- Enhanced Booking Model for Escrow System ---
class Booking(models.Model):
    """
    Model to represent a booking in the escrow system.
    Handles the full flow: saved -> paid -> confirmed/cancelled -> released/refunded
    """
    STATUS_CHOICES = [
        ('saved', 'Saved'),
        ('paid_pending_confirmation', 'Paid - Awaiting Confirmation'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
        ('released', 'Funds Released'), # This status might be redundant if using release_status, but kept for consistency
    ]

    REFUND_STATUS_CHOICES = [
        ('none', 'None'),
        ('requested', 'Requested'),
        ('processed', 'Processed'),
    ]

    RELEASE_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('released', 'Released'),
    ]

    PAYMENT_TYPE_CHOICES = [
        ('security_deposit', 'Security Deposit'),
        ('first_month_rent', 'First Month Rent'),
        ('booking_fee', 'Booking Fee'),
        ('full_rent', 'Full Rent'),
        ('hotel_stay', 'Hotel Stay'),
    ]

    LISTING_TYPE_CHOICES = [
        ('landlord_listing', 'Landlord Listing'),
        ('agent_listing', 'Agent Listing'),
        ('hotel_listing', 'Hotel Listing'),
    ]

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookings'
    )
    listing_type = models.CharField(max_length=20, choices=LISTING_TYPE_CHOICES)
    listing_id = models.IntegerField()

    # Payment tracking
    initial_amount_paid_ngn = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES, null=True, blank=True)

    # Status tracking
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='saved')

    # Refund/Release tracking
    refund_status = models.CharField(max_length=20, choices=REFUND_STATUS_CHOICES, default='none')
    release_status = models.CharField(max_length=20, choices=RELEASE_STATUS_CHOICES, default='pending')
    refund_processed_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    payout_reference = models.CharField(max_length=100, null=True, blank=True)  # For tracking fund release
    # ✅ NEW: Add funds_released field
    funds_released = models.BooleanField(default=False, help_text="Have the funds been released to the landlord/owner?")

    # Booking details (for hotels)
    check_in_date = models.DateField(null=True, blank=True)
    check_out_date = models.DateField(null=True, blank=True)

    # Link to the payment if one exists for this booking
    lease_payment = models.OneToOneField(
        LeasePayment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='booking' # Allows reverse lookup from LeasePayment to Booking
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Booking {self.id} - {self.user.username} - {self.status}"

    # Property title helper
    @property
    def property_title(self):
        listing_obj = self.get_related_published_listing()
        if listing_obj:
            if self.listing_type == 'hotel_listing':
                 return getattr(listing_obj, 'name', f'Hotel Listing {self.listing_id}')
            else:
                 return getattr(listing_obj, 'title', f'Listing {self.listing_id}')
        return f'Listing {self.listing_id}'

    # Property rent/price helper
    @property
    def property_price(self):
        listing_obj = self.get_related_published_listing()
        if listing_obj:
            if self.listing_type == 'hotel_listing':
                 return getattr(listing_obj, 'price_per_night', 'N/A')
            else:
                 return getattr(listing_obj, 'monthly_rent', 'N/A')
        return 'N/A'

    # Check if booking is in cancellation window (e.g., 24 hours)
    @property
    def is_in_cancellation_window(self):
        time_since_creation = timezone.now() - self.created_at
        return time_since_creation <= timedelta(hours=24)  # Adjust hours as needed

    # Check if booking is in confirmation window (e.g., 48 hours after payment)
    @property
    def is_in_confirmation_window(self):
        # ✅ UPDATED: Check based on status and updated_at (when status last changed to paid_pending_confirmation)
        # This logic assumes updated_at is updated when status changes to 'paid_pending_confirmation'
        if self.status != 'paid_pending_confirmation':
            return False
            
        time_since_payment = timezone.now() - self.updated_at
        return time_since_payment <= timedelta(hours=48)  # Adjust hours as needed

    # Get the related published listing object
    def get_related_published_listing(self):
        if self.listing_type == 'landlord_listing':
            try:
                from listings.models import Property
                return Property.objects.get(id=self.listing_id)
            except (ImportError, Property.DoesNotExist):
                return None
        elif self.listing_type == 'agent_listing':
            try:
                from agent_listings.models import AgentProperty
                return AgentProperty.objects.get(id=self.listing_id)
            except (ImportError, AgentProperty.DoesNotExist):
                return None
        elif self.listing_type == 'hotel_listing':
            try:
                from hotels.models import HotelListing
                return HotelListing.objects.get(id=self.listing_id)
            except (ImportError, HotelListing.DoesNotExist):
                return None
        return None

    # Get the landlord/agent account details (will be populated later when you update listing APIs)
    def get_landlord_account_details(self):
        """
        Get the account details of the property owner.
        This will return None initially until you update listing models to collect account details.
        """
        listing = self.get_related_published_listing()
        if listing:
            # These fields will be added to your listing models later
            account_details = {
                'bank_name': getattr(listing, 'owner_bank_name', None),
                'account_number': getattr(listing, 'owner_account_number', None),
                'account_name': getattr(listing, 'owner_account_name', None),
                'bank_verified': getattr(listing, 'bank_verified', False),
            }
            return account_details
        return None

    # ✅ UPDATED: Check if funds can be released (requires account details and status)
    def can_release_funds(self):
        # Check status, payment amount, and if funds were already released
        if self.status != 'confirmed' or self.initial_amount_paid_ngn <= 0 or self.funds_released:
            return False

        # Check if account details are available and verified
        account_details = self.get_landlord_account_details()
        if not account_details:
            return False

        return (
            account_details['bank_name'] and 
            account_details['account_number'] and 
            account_details['account_name'] and
            account_details['bank_verified']
        )

    # ✅ NEW: Helper method to mark funds as released
    def mark_funds_released(self, payout_reference=None):
        """Mark the booking as having its funds released."""
        self.funds_released = True
        self.release_status = 'released'
        self.released_at = timezone.now()
        if payout_reference:
            self.payout_reference = payout_reference
        self.save(update_fields=['funds_released', 'release_status', 'released_at', 'payout_reference'])