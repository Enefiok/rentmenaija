from django.db import models
from django.conf import settings  # Use your custom user model

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
        return None


# --- New Model for Bookings (Saved Properties) ---
class Booking(models.Model):
    """
    Model to represent a saved property booking by a user (like an item in a cart).
    Can be saved without payment, or linked to a payment after payment is made.
    """
    STATUS_CHOICES = [
        ('saved', 'Saved (Not Paid)'),
        ('paid_pending_confirmation', 'Paid, Pending Confirmation'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ]

    LISTING_TYPE_CHOICES = [
        ('landlord_listing', 'Landlord Listing'),
        ('agent_listing', 'Agent Listing'),
    ]

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookings'
    )
    listing_type = models.CharField(max_length=20, choices=LISTING_TYPE_CHOICES)
    # Store the ID of the related listing (either Property or AgentProperty, the published one)
    listing_id = models.IntegerField()

    # Link to the payment if one exists for this booking
    lease_payment = models.OneToOneField(
        LeasePayment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='booking' # Allows reverse lookup from LeasePayment to Booking
    )

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='saved')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Booking {self.id} by {self.user.username} for {self.get_listing_type_display()} ID {self.listing_id} - Status: {self.status}"

    # Optional: Method to get the related published listing object for logic
    def get_related_published_listing(self):
        if self.listing_type == 'landlord_listing':
            try:
                from listings.models import Property # Link to the published Property
                return Property.objects.get(id=self.listing_id)
            except (ImportError, Property.DoesNotExist):
                return None
        elif self.listing_type == 'agent_listing':
            try:
                from agent_listings.models import AgentProperty # Link to the published AgentProperty
                return AgentProperty.objects.get(id=self.listing_id)
            except (ImportError, AgentProperty.DoesNotExist):
                return None
        return None

    # Optional: Method to get the related draft listing object (if needed for details)
    def get_related_draft_listing(self):
        if self.listing_type == 'landlord_listing':
            try:
                from listings.models import PropertyDraft # Link to the PropertyDraft
                return PropertyDraft.objects.get(id=self.listing_id)
            except (ImportError, PropertyDraft.DoesNotExist):
                return None
        elif self.listing_type == 'agent_listing':
            try:
                from agent_listings.models import AgentPropertyDraft # Link to the AgentPropertyDraft
                return AgentPropertyDraft.objects.get(id=self.listing_id)
            except (ImportError, AgentPropertyDraft.DoesNotExist):
                return None
        return None

    # Property title helper (fetches from draft or published listing)
    @property
    def property_title(self):
        listing_obj = self.get_related_draft_listing() or self.get_related_published_listing()
        if listing_obj:
            # Assuming the draft and published models have a 'title' field
            # Adjust attribute name if different (e.g., 'name' for hotels)
            return getattr(listing_obj, 'title', f'Listing {self.listing_id}')
        return f'Listing {self.listing_id}'

    # Property rent helper (fetches from draft or published listing)
    @property
    def property_rent(self):
        listing_obj = self.get_related_draft_listing() or self.get_related_published_listing()
        if listing_obj:
            # Assuming the draft and published models have a 'monthly_rent' field
            # Adjust attribute name if different (e.g., 'price_per_night' for hotels)
            return getattr(listing_obj, 'monthly_rent', 'N/A')
        return 'N/A'

# --- End of New Model ---