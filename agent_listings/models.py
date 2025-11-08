# agent_listings/models.py
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

# Property type choices (copied from listings/)
PROPERTY_TYPE_CHOICES = [
    ('apartment', 'Apartment'),
    ('duplex', 'Duplex'),
    ('bungalow', 'Bungalow'),
    ('terraced_house', 'Terraced House'),
    ('mansion', 'Mansion'),
    ('mini_flat', 'Mini Flat'),
    ('self_contain', 'Self Contain'),
]


class AgentPropertyDraft(models.Model):
    # The agent doing the listing
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='agent_drafts')

    # Landlord info (required since agent is listing for someone else)
    landlord_name = models.CharField(max_length=200)
    landlord_phone = models.CharField(max_length=15)
    landlord_email = models.EmailField(blank=True, null=True)

    # Property Info
    title = models.CharField(max_length=200, blank=True, null=True)
    monthly_rent = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='NGN')
    lease_term_preference = models.CharField(max_length=20, choices=LEASE_TERM_CHOICES, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    known_issues = models.TextField(blank=True, null=True)
    house_rules = models.TextField(blank=True, null=True)
    images = models.JSONField(default=list, blank=True)  # Stores Cloudinary image URLs

    # ✅ ADD property_type
    property_type = models.CharField(max_length=50, choices=PROPERTY_TYPE_CHOICES, blank=True, null=True)

    # Location
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

    # Agent Agreements
    is_authorised_to_list = models.BooleanField(default=False)
    details_accurate = models.BooleanField(default=False)
    assume_responsibility_for_fraud = models.BooleanField(default=False)
    agrees_to_escrow_process = models.BooleanField(default=False)
    digital_signature = models.CharField(max_length=100, blank=True, null=True)
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
        agent = self.agent
        agent_display = agent.get_full_name().strip() or agent.email
        return f"Agent Draft: {self.title or 'Untitled'} by {agent_display} (for {self.landlord_name})"

    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Agent Property Draft"
        verbose_name_plural = "Agent Property Drafts"


class AgentProperty(models.Model):
    draft = models.OneToOneField(AgentPropertyDraft, on_delete=models.CASCADE)
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
        return f"[AGENT] {title} → {self.get_status_display()}"

    class Meta:
        verbose_name = "Agent-Submitted Property"
        verbose_name_plural = "Agent-Submitted Properties"