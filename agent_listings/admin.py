# agent_listings/admin.py

from django.contrib import admin
from django.utils.safestring import mark_safe
from django.utils.html import format_html
from .models import AgentPropertyDraft, AgentProperty


# === Helper: Format Nigerian Naira (or any currency) nicely ===
def format_currency(amount, currency='NGN'):
    symbols = {'NGN': '₦', 'USD': '$', 'GHS': '₵', 'KES': 'KSh'}
    symbol = symbols.get(currency, currency)
    try:
        amount = f"{float(amount):,.2f}"
    except (ValueError, TypeError):
        amount = "0.00"
    return f"{symbol}{amount}"


# === ADMIN FOR DRAFTS ===
@admin.register(AgentPropertyDraft)
class AgentPropertyDraftAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'get_rent_display',
        'lease_term_preference',
        'agent_link',
        'landlord_name',
        'landlord_phone',
        'address_truncated',
        'image_thumbnail',
        'submitted_badge',
        'created_at',
        'updated_at',
    )
    list_filter = (
        'submitted_for_review',
        'lease_term_preference',
        'currency',
        'created_at',
        'updated_at',
    )
    search_fields = (
        'title',
        'agent__username',
        'agent__email',
        'landlord_name',
        'landlord_phone',
        'address',
        'description',
    )
    readonly_fields = ('created_at', 'updated_at', 'signed_at')
    actions = ['mark_submitted', 'mark_not_submitted']

    def get_rent_display(self, obj):
        return format_currency(obj.monthly_rent, obj.currency)
    get_rent_display.short_description = "Rent"
    get_rent_display.admin_order_field = 'monthly_rent'

    def agent_link(self, obj):
        url = f"/admin/accounts/user/{obj.agent.id}/change/"
        return format_html('<a href="{}">{}</a>', url, obj.agent.email or obj.agent.username)
    agent_link.short_description = "Agent"
    agent_link.admin_order_field = 'agent__email'

    def address_truncated(self, obj):
        return obj.address if len(obj.address) < 50 else obj.address[:47] + "..."
    address_truncated.short_description = "Address"
    address_truncated.admin_order_field = 'address'

    def image_thumbnail(self, obj):
        images = obj.images
        if not images:
            return "❌ No Image"
        first_image = images[0]
        return format_html(
            '<img src="{}" style="width:60px;height:45px;object-fit:cover;border-radius:4px;" />',
            first_image
        )
    image_thumbnail.short_description = "Image"

    def submitted_badge(self, obj):
        if obj.submitted_for_review:
            return format_html("<strong style='color:green;'>✔️ Yes</strong>")
        return format_html("<span style='color:orange;'>🟡 No</span>")
    submitted_badge.short_description = "Submitted?"
    submitted_badge.admin_order_field = 'submitted_for_review'

    # === Fieldsets (Edit Page Layout) ===
    fieldsets = (
        ("📋 Agent & Landlord Info", {
            "fields": ("agent", "landlord_name", "landlord_phone", "landlord_email")
        }),
        ("🏠 Property Details", {
            "fields": ("title", "monthly_rent", "currency", "lease_term_preference",
                       "description", "known_issues", "house_rules")
        }),
        ("📍 Location", {
            "fields": ("address", "latitude", "longitude")
        }),
        ("🖼️ Images", {
            "fields": ("images",),
            "classes": ("collapse",)
        }),
        ("✅ Agreements", {
            "fields": (
                "is_authorised_to_list",
                "details_accurate",
                "assume_responsibility_for_fraud",
                "agrees_to_escrow_process",
                "digital_signature",
                "signed_at"
            )
        }),
        ("📅 Metadata", {
            "fields": ("created_at", "updated_at", "submitted_for_review"),
            "classes": ("collapse",)
        }),
    )

    def mark_submitted(self, request, queryset):
        updated = queryset.filter(submitted_for_review=False).update(submitted_for_review=True)
        self.message_user(request, f"✅ Marked {updated} draft(s) as submitted.")
    mark_submitted.short_description = "✅ Mark selected drafts as submitted"

    def mark_not_submitted(self, request, queryset):
        updated = queryset.filter(submitted_for_review=True).update(submitted_for_review=False)
        self.message_user(request, f"🟡 Marked {updated} draft(s) as not submitted.")
    mark_not_submitted.short_description = "🟡 Mark selected drafts as not submitted"


# === ADMIN FOR APPROVAL (AgentProperty) ===
@admin.register(AgentProperty)
class AgentPropertyAdmin(admin.ModelAdmin):

    # === CUSTOM COLUMNS FOR LIST VIEW ===

    def property_title(self, obj):
        return obj.draft.title or "Untitled Listing"
    property_title.short_description = "Title"
    property_title.admin_order_field = 'draft__title'

    def agent_name(self, obj):
        user = obj.draft.agent
        return f"{user.get_full_name() or user.username} ({user.email})"
    agent_name.short_description = "Agent"

    def status_with_reason(self, obj):
        if obj.status == 'approved':
            badge = format_html('<span style="color: green; font-weight: bold;">✅ Approved</span>')
        elif obj.status == 'rejected':
            badge = format_html('<span style="color: red; font-weight: bold;">❌ Rejected</span>')
        else:
            badge = format_html('<span style="color: orange; font-weight: bold;">🟡 Pending</span>')
        return badge
    status_with_reason.short_description = "Status"

    def monthly_rent(self, obj):
        return format_currency(obj.draft.monthly_rent, obj.draft.currency)
    monthly_rent.short_description = "Rent"
    monthly_rent.admin_order_field = 'draft__monthly_rent'

    def currency(self, obj):
        return obj.draft.currency
    currency.short_description = "Currency"

    def lease_term_preference(self, obj):
        return obj.draft.lease_term_preference.replace('_', ' ').title()
    lease_term_preference.short_description = "Lease Term"

    def landlord_name(self, obj):
        return obj.draft.landlord_name
    landlord_name.short_description = "Landlord Name"

    def landlord_phone(self, obj):
        return obj.draft.landlord_phone
    landlord_phone.short_description = "Landlord Phone"

    def landlord_email(self, obj):
        return obj.draft.landlord_email or "—"
    landlord_email.short_description = "Landlord Email"

    def short_address(self, obj):
        addr = obj.draft.address
        return addr[:50] + "..." if len(addr) > 50 else addr
    short_address.short_description = "Address"
    short_address.admin_order_field = 'draft__address'

    def submitted_at(self, obj):
        return obj.draft.created_at
    submitted_at.short_description = "Submitted At"
    submitted_at.admin_order_field = 'draft__created_at'

    def description_preview(self, obj):
        desc = obj.draft.description or "No description."
        return format_html("<div style='max-width:200px; font-size:0.9em;'>{}</div>", desc)
    description_preview.short_description = "Description"

    def known_issues_preview(self, obj):
        issues = obj.draft.known_issues or "None reported."
        color = "red" if "leak" in issues.lower() or "repair" in issues.lower() else "gray"
        return format_html("<span style='color:{}'>{}</span>", color, issues)
    known_issues_preview.short_description = "Known Issues"

    def house_rules_preview(self, obj):
        rules = obj.draft.house_rules or "Not specified."
        return format_html("<small>{}</small>", rules)
    house_rules_preview.short_description = "House Rules"

    def image_thumbnail(self, obj):
        images = obj.draft.images
        if not images:
            return "❌ No"
        first_img = images[0]
        return format_html(
            '<img src="{}" style="width: 80px; height: 60px; object-fit: cover; border-radius: 4px;" />',
            first_img
        )
    image_thumbnail.short_description = "Image"

    def signature_info(self, obj):
        sig = obj.draft.digital_signature or "Not signed"
        time = obj.draft.signed_at.strftime("%b %d, %H:%M") if obj.draft.signed_at else "—"
        return format_html("{}<br><small>{}</small>", sig, time)
    signature_info.short_description = "Signature / Time"

    def is_authorised_verified(self, obj):
        val = obj.draft.is_authorised_to_list
        return format_html("✅ Yes") if val else format_html("⚠️ No")
    is_authorised_verified.short_description = "Authorised?"

    def details_verified(self, obj):
        val = obj.draft.details_accurate
        return format_html("✅ Yes") if val else format_html("❌ No")
    details_verified.short_description = "Details Accurate?"

    def fraud_responsible(self, obj):
        val = obj.draft.assume_responsibility_for_fraud
        return format_html("✅ Yes") if val else format_html("❌ No")
    fraud_responsible.short_description = "Responsible for Fraud?"

    def allow_escrow_status(self, obj):
        val = obj.draft.agrees_to_escrow_process
        return format_html("✅ Yes") if val else format_html("❌ No")
    allow_escrow_status.short_description = "Allow Escrow?"

    def submitted_for_review_status(self, obj):
        val = obj.draft.submitted_for_review
        return format_html("<strong style='color:green'>YES</strong>") if val else format_html("<strong style='color:red'>NO</strong>")
    submitted_for_review_status.short_description = "Submitted?"
    submitted_for_review_status.admin_order_field = 'draft__submitted_for_review'

    def approved_by_info(self, obj):
        if obj.approved_by:
            return format_html("{}<br><small>{}</small>", obj.approved_by.username, obj.approved_at.strftime("%b %d"))
        return "—"
    approved_by_info.short_description = "Approved By / When"

    # === FULL LIST VIEW WITH ALL FIELDS VISIBLE AT A GLANCE ===
    list_display = (
        'property_title',
        'agent_name',
        'status_with_reason',
        'monthly_rent',
        'currency',
        'lease_term_preference',
        'landlord_name',
        'landlord_phone',
        'short_address',
        'submitted_at',
        'image_thumbnail',
        'description_preview',
        'known_issues_preview',
        'house_rules_preview',
        'signature_info',
        'is_authorised_verified',
        'details_verified',
        'fraud_responsible',
        'allow_escrow_status',
        'submitted_for_review_status',
        'approved_by_info',
    )

    # === FILTERING & SEARCHING ===
    list_filter = (
        'status',
        'approved_at',
        'published_at',
        ('draft__submitted_for_review', admin.BooleanFieldListFilter),
        'draft__lease_term_preference',
        'draft__currency',
        'draft__created_at',
    )

    search_fields = (
        'draft__title',
        'draft__description',
        'draft__address',
        'draft__known_issues',
        'draft__house_rules',
        'draft__agent__username',
        'draft__agent__email',
        'approved_by__username',
        'draft__landlord_name',
        'draft__landlord_phone',
    )

    date_hierarchy = 'draft__created_at'

    # === DETAIL VIEW FIELDSETS ===
    fieldsets = (
        ("📋 Listing Overview", {
            "fields": ("property_title", "agent_name", "submitted_at"),
            "classes": ("wide",),
        }),
        ("📍 Location & Address", {
            "fields": (
                "full_address",
                "latitude",
                "longitude"
            ),
            "classes": ("wide",),
        }),
        ("📄 Full Details", {
            "fields": (
                "description",
                "known_issues",
                "house_rules",
                "image_thumbnails",
            ),
            "classes": ("wide",),
        }),
        ("💰 Financial Info", {
            "fields": (
                "formatted_monthly_rent",
                "currency",
                "lease_term_preference_detail",
                "landlord_contact_info"
            ),
            "classes": ("wide",),
        }),
        ("✅ Approval Status", {
            "fields": (
                "status",
                "approved_by",
                "approved_at",
                "rejected_reason",
                "published_at"
            ),
            "classes": ("wide",),
        }),
    )

    readonly_fields = (
        'full_address',
        'latitude',
        'longitude',
        'description',
        'known_issues',
        'house_rules',
        'image_thumbnails',
        'formatted_monthly_rent',
        'currency',
        'lease_term_preference_detail',
        'landlord_contact_info',
        'approved_at',
        'published_at',
        'approved_by',
        'status'
    )

    def full_address(self, obj):
        return obj.draft.address or "-"
    full_address.short_description = "Full Address"

    def latitude(self, obj):
        return obj.draft.latitude
    latitude.short_description = "Latitude"

    def longitude(self, obj):
        return obj.draft.longitude
    longitude.short_description = "Longitude"

    def description(self, obj):
        return obj.draft.description or "No description provided."
    description.short_description = "Description"

    def known_issues(self, obj):
        return obj.draft.known_issues or "No known issues reported."
    known_issues.short_description = "Known Issues"

    def house_rules(self, obj):
        return obj.draft.house_rules or "No house rules specified."
    house_rules.short_description = "House Rules"

    def image_thumbnails(self, obj):
        if not obj.draft.images:
            return "No images uploaded."
        html = "<div style='display: flex; gap: 10px; flex-wrap: wrap;'>"
        for url in obj.draft.images:
            html += f"<img src='{url}' style='width: 150px; height: 120px; object-fit: cover; border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);' />"
        html += "</div>"
        return mark_safe(html)
    image_thumbnails.short_description = "Image Gallery"

    def formatted_monthly_rent(self, obj):
        return format_currency(obj.draft.monthly_rent, obj.draft.currency)
    formatted_monthly_rent.short_description = "Monthly Rent"

    def lease_term_preference_detail(self, obj):
        return obj.draft.lease_term_preference.replace('_', ' ').title()
    lease_term_preference_detail.short_description = "Lease Term"

    def landlord_contact_info(self, obj):
        d = obj.draft
        name = d.landlord_name or "Not provided"
        phone = d.landlord_phone or "No phone"
        email = d.landlord_email or "No email"
        return format_html(f"{name}<br>{phone}<br>{email}")
    landlord_contact_info.short_description = "Landlord Contact"

    # === SECURITY & UX ===
    def has_add_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('status',)
        return self.readonly_fields

    actions = ['approve_selected', 'reject_selected']

    def approve_selected(self, request, queryset):
        updated = 0
        for prop in queryset:
            if prop.status == 'pending':
                prop.approve(request.user)
                updated += 1
        self.message_user(request, f"✅ Successfully approved {updated} listing(s).")

    approve_selected.short_description = "✅ Approve selected listings"

    def reject_selected(self, request, queryset):
        updated = 0
        for prop in queryset:
            if prop.status == 'pending':
                prop.reject(request.user, reason="Not specified")
                updated += 1
        self.message_user(request, f"❌ Rejected {updated} listing(s).")

    reject_selected.short_description = "❌ Reject selected listings"