# agent_listings/models.py

from django.db import models
from django.conf import settings
from django.utils import timezone

CURRENCY_CHOICES = [
    ('NGN', 'Nigerian Naira'),
    ('USD', 'US Dollar'),
    ('GHS', 'Ghana Cedi'),
    ('KES', 'Kenyan Shilling'),
]

LEASE_TERM_CHOICES = [
    ('monthly', 'Monthly'),
    ('6_months', '6 Months'),
    ('1_year', '1 Year'),
    ('2_years', '2 Years'),
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
    images = models.JSONField(default=list, blank=True)

    # Location
    address = models.CharField(max_length=500, blank=True, null=True)
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)

    # Agent Agreements (more formalized)
    is_authorised_to_list = models.BooleanField(default=False)  # "I have permission from the landlord"
    details_accurate = models.BooleanField(default=False)
    assume_responsibility_for_fraud = models.BooleanField(default=False)
    agrees_to_escrow_process = models.BooleanField(default=False)
    digital_signature = models.CharField(max_length=100, blank=True, null=True)
    signed_at = models.DateTimeField(blank=True, null=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_for_review = models.BooleanField(default=False)

    def __str__(self):
        return f"Agent Draft: {self.title or 'Untitled'} by {self.agent.username} (for {self.landlord_name})"

    class Meta:
        ordering = ['-updated_at']


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

    def approve(self, admin_user):
        self.status = 'approved'
        self.approved_by = admin_user
        self.approved_at = timezone.now()
        self.published_at = timezone.now()
        self.save()

    def reject(self, admin_user, reason=""):
        self.status = 'rejected'
        self.approved_by = admin_user
        self.rejected_reason = reason
        self.save()

    def __str__(self):
        return f"[AGENT] {self.draft.title} → {self.status}"