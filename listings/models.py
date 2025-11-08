# listings/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone

# Currency choices
CURRENCY_CHOICES = [
    ('NGN', 'Nigerian Naira'),
    ('USD', 'US Dollar'),
    ('GHS', 'Ghana Cedi'),
    ('KES', 'Kenyan Shilling'),
]

# Lease term preferences
LEASE_TERM_CHOICES = [
    ('monthly', 'Monthly'),
    ('6_months', '6 Months'),
    ('1_year', '1 Year'),
    ('2_years', '2 Years'),
]

# Property type choices
PROPERTY_TYPE_CHOICES = [
    ('apartment', 'Apartment'),
    ('duplex', 'Duplex'),
    ('bungalow', 'Bungalow'),
    ('terraced_house', 'Terraced House'),
    ('mansion', 'Mansion'),
    ('mini_flat', 'Mini Flat'),
    ('self_contain', 'Self Contain'),
]


class PropertyDraft(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    # Step 1: Basic Info
    title = models.CharField(max_length=200, blank=True, null=True)
    monthly_rent = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='NGN')
    lease_term_preference = models.CharField(max_length=20, choices=LEASE_TERM_CHOICES, blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    known_issues = models.TextField(blank=True, null=True)
    house_rules = models.TextField(blank=True, null=True)
    images = models.JSONField(default=list, blank=True)  # Stores Cloudinary image URLs

    # Property type
    property_type = models.CharField(max_length=50, choices=PROPERTY_TYPE_CHOICES, blank=True, null=True)

    # Step 2: Location
    address = models.CharField(max_length=500, blank=True, null=True)
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)

    # ✅ NEW: Bank account details for the property owner (landlord)
    owner_bank_name = models.CharField(max_length=100, blank=True, null=True, help_text="Bank name of the property owner")
    owner_account_number = models.CharField(max_length=20, blank=True, null=True, help_text="Account number of the property owner")
    owner_account_name = models.CharField(max_length=200, blank=True, null=True, help_text="Account name of the property owner")
    bank_verified = models.BooleanField(default=False, help_text="Whether the bank details have been verified")

    # Step 3: Confirmations
    is_owner_or_representative = models.BooleanField(default=False)
    details_accurate = models.BooleanField(default=False)
    responsible_for_fraud = models.BooleanField(default=False)
    allow_escrow = models.BooleanField(default=False)
    signature = models.CharField(max_length=100, blank=True, null=True)
    signed_at = models.DateTimeField(blank=True, null=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_for_review = models.BooleanField(default=False)

    def add_image_url(self, url):
        """Safely append a Cloudinary image URL to the images list."""
        if not isinstance(self.images, list):
            self.images = []
        if url and url not in self.images:
            self.images.append(url)
        self.save(update_fields=['images'])

    def remove_image_url(self, url):
        """Remove a Cloudinary image URL from the images list."""
        if isinstance(self.images, list) and url in self.images:
            self.images.remove(url)
            self.save(update_fields=['images'])

    def __str__(self):
        user = self.user
        # Prefer full name, fall back to email (never username)
        display_name = user.get_full_name().strip() or user.email
        return f"Draft: {self.title or 'Untitled'} by {display_name}"

    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Property Draft"
        verbose_name_plural = "Property Drafts"


class Property(models.Model):
    draft = models.OneToOneField(PropertyDraft, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')],
        default='pending'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True, null=True)
    published_at = models.DateTimeField(null=True, blank=True)

    # ✅ NEW: Bank account details for the property owner (landlord) - copied from draft after approval
    owner_bank_name = models.CharField(max_length=100, blank=True, null=True, help_text="Bank name of the property owner")
    owner_account_number = models.CharField(max_length=20, blank=True, null=True, help_text="Account number of the property owner")
    owner_account_name = models.CharField(max_length=200, blank=True, null=True, help_text="Account name of the property owner")
    bank_verified = models.BooleanField(default=False, help_text="Whether the bank details have been verified")

    def approve(self, admin_user):
        if self.status != 'pending':
            return
        self.status = 'approved'
        self.approved_by = admin_user
        self.approved_at = timezone.now()
        self.published_at = timezone.now()
        
        # ✅ NEW: Copy bank details from the draft when approving
        draft = self.draft
        self.owner_bank_name = draft.owner_bank_name
        self.owner_account_number = draft.owner_account_number
        self.owner_account_name = draft.owner_account_name
        self.bank_verified = draft.bank_verified
        
        self.save()

    def reject(self, admin_user, reason=""):
        if self.status != 'pending':
            return
        self.status = 'rejected'
        self.approved_by = admin_user
        self.rejected_reason = reason
        self.save()

    def __str__(self):
        title = self.draft.title or 'Untitled'
        return f"Property: {title} [{self.get_status_display()}]"

    class Meta:
        verbose_name = "Approved Property"
        verbose_name_plural = "Approved Properties"