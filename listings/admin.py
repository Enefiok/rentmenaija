# listings/admin.py

from django.contrib import admin
from django.utils.safestring import mark_safe
from django.utils.html import format_html  # For rich display
from .models import PropertyDraft, Property


# === ADMIN FOR PROPERTY DRAFTS ===
@admin.register(PropertyDraft)
class PropertyDraftAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'user',
        'phone_number',
        'address',
        'bank_details_summary', # NEW: Show bank details summary in list
        'submitted_for_review',
        'created_at'
    )
    list_filter = (
        'submitted_for_review',
        'currency',
        'lease_term_preference',
        'created_at',
        # ✅ NEW: Add bank verification filter
        ('bank_verified', admin.BooleanFieldListFilter),
    )
    search_fields = (
        'title',
        'user__username',
        'user__email',
        'phone_number',
        'address',
        # ✅ NEW: Add bank fields to search
        'owner_bank_name',
        'owner_account_number',
    )
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ("Basic Information", {
            "fields": ("title", "user", "monthly_rent", "currency", "lease_term_preference")
        }),
        ("Contact & Description", {
            "fields": ("phone_number", "description", "known_issues", "house_rules")
        }),
        ("📍 Location", {
            "fields": ("address", "latitude", "longitude")
        }),
        ("💳 Bank Account Details", { # NEW: Add bank details fieldset
            "fields": ("owner_bank_name", "owner_account_number", "owner_account_name", "bank_verified"),
            "classes": ("collapse",) # Collapse by default to keep interface clean
        }),
        ("🖼️ Images", {
            "fields": ("images",),
            "classes": ("collapse",)
        }),
        ("✅ Agreements", {
            "fields": (
                "is_owner_or_representative",
                "details_accurate",
                "responsible_for_fraud",
                "allow_escrow",
                "signature",
                "signed_at"
            )
        }),
        ("📅 Metadata", {
            "fields": ("created_at", "updated_at", "submitted_for_review"),
            "classes": ("collapse",)
        }),
    )

    # ✅ NEW: Bank Details Summary Column
    def bank_details_summary(self, obj):
        if not obj.owner_account_number:
            return format_html("<span style='color: red;'>❌ No Bank Details</span>")
        status = "✅ Verified" if obj.bank_verified else "🟡 Pending"
        return format_html(
            "<div>{}</div><div style='font-size: 0.8em; color: gray;'>{}</div>",
            f"{obj.owner_bank_name} - {obj.owner_account_number}",
            status
        )
    bank_details_summary.short_description = "Bank Details"


# === ADMIN FOR FINAL LISTINGS (REVIEW & APPROVAL) ===
@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):

    # === CUSTOM COLUMNS FOR LIST VIEW ===
    # Added defensive checks for obj.draft in all list_display methods
    def property_title(self, obj):
        if not obj.draft:
            return format_html("<span style='color: red;'>❌ Draft Missing</span>")
        return obj.draft.title or "Untitled Listing"
    property_title.short_description = "Title"
    property_title.admin_order_field = 'draft__title'

    def owner_name(self, obj):
        if not obj.draft or not obj.draft.user:
            return format_html("<span style='color: red;'>❌ Owner Missing</span>")
        user = obj.draft.user
        return f"{user.get_full_name() or user.username} ({user.email})"
    owner_name.short_description = "Owner"

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
        if not obj.draft or obj.draft.monthly_rent is None:
            return format_html("<span style='color: red;'>❌ Rent Missing</span>")
        return f"₦{obj.draft.monthly_rent:,.0f}"
    monthly_rent.short_description = "Rent"
    monthly_rent.admin_order_field = 'draft__monthly_rent'

    def currency(self, obj):
        if not obj.draft:
            return "—"
        return obj.draft.currency
    currency.short_description = "Currency"

    def lease_term_preference(self, obj):
        if not obj.draft:
            return "—"
        return obj.draft.lease_term_preference.replace('_', ' ').title()
    lease_term_preference.short_description = "Lease Term"

    def phone_number(self, obj):
        if not obj.draft:
            return "—"
        return obj.draft.phone_number
    phone_number.short_description = "Phone"
    phone_number.admin_order_field = 'draft__phone_number'

    # ✅ NEW: Bank Info Columns for List View
    def owner_bank_name(self, obj):
        if not obj.draft:
            return "—"
        return obj.draft.owner_bank_name or "—"
    owner_bank_name.short_description = "Bank Name"

    def owner_account_number(self, obj):
        if not obj.draft:
            return "—"
        return obj.draft.owner_account_number or "—"
    owner_account_number.short_description = "Account Number"

    def bank_verified_status(self, obj):
        if not obj.draft:
            return format_html("❌ Draft Missing")
        verified = obj.draft.bank_verified
        return format_html("✅ Yes") if verified else format_html("❌ No")
    bank_verified_status.short_description = "Bank Verified?"

    def short_address(self, obj):
        if not obj.draft:
            return format_html("<span style='color: red;'>❌ Address Missing</span>")
        addr = obj.draft.address
        return addr[:50] + "..." if len(addr) > 50 else addr
    short_address.short_description = "Address"
    short_address.admin_order_field = 'draft__address'

    def submitted_at(self, obj):
        if not obj.draft:
            return "—"
        return obj.draft.created_at
    submitted_at.short_description = "Submitted At"
    submitted_at.admin_order_field = 'draft__created_at'

    def description_preview(self, obj):
        if not obj.draft:
            return format_html("<span style='color: red;'>❌ Description Missing</span>")
        desc = obj.draft.description or "No description."
        return format_html("<div style='max-width:200px; font-size:0.9em;'>{}</div>", desc)
    description_preview.short_description = "Description"

    def known_issues_preview(self, obj):
        if not obj.draft:
            return format_html("<span style='color: red;'>❌ Known Issues Missing</span>")
        issues = obj.draft.known_issues or "None reported."
        color = "red" if "leak" in issues.lower() or "repair" in issues.lower() else "gray"
        return format_html("<span style='color:{}'>{}</span>", color, issues)
    known_issues_preview.short_description = "Known Issues"

    def house_rules_preview(self, obj):
        if not obj.draft:
            return format_html("<span style='color: red;'>❌ House Rules Missing</span>")
        rules = obj.draft.house_rules or "Not specified."
        return format_html("<small>{}</small>", rules)
    house_rules_preview.short_description = "House Rules"

    def image_thumbnail(self, obj):
        if not obj.draft:
            return format_html("<span style='color: red;'>❌ Image Missing</span>")
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
        if not obj.draft:
            return format_html("<span style='color: red;'>❌ Signature Missing</span>")
        sig = obj.draft.signature or "Not signed"
        time = obj.draft.signed_at.strftime("%b %d, %H:%M") if obj.draft.signed_at else "—"
        return format_html("{}<br><small>{}</small>", sig, time)
    signature_info.short_description = "Signature / Time"

    def is_owner_verified(self, obj):
        if not obj.draft:
            return format_html("❌ Draft Missing")
        val = obj.draft.is_owner_or_representative
        return format_html("✅ Yes") if val else format_html("⚠️ No")
    is_owner_verified.short_description = "Owner?"

    def details_verified(self, obj):
        if not obj.draft:
            return format_html("❌ Draft Missing")
        val = obj.draft.details_accurate
        return format_html("✅ Yes") if val else format_html("❌ No")
    details_verified.short_description = "Details Accurate?"

    def fraud_responsible(self, obj):
        if not obj.draft:
            return format_html("❌ Draft Missing")
        val = obj.draft.responsible_for_fraud
        return format_html("✅ Yes") if val else format_html("❌ No")
    fraud_responsible.short_description = "Responsible for Fraud?"

    def allow_escrow_status(self, obj):
        if not obj.draft:
            return format_html("❌ Draft Missing")
        val = obj.draft.allow_escrow
        return format_html("✅ Yes") if val else format_html("❌ No")
    allow_escrow_status.short_description = "Allow Escrow?"

    def submitted_for_review_status(self, obj):
        if not obj.draft:
            return format_html("❌ Draft Missing")
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
        'owner_name',
        'status_with_reason',
        'monthly_rent',
        'currency',
        'lease_term_preference',
        'phone_number',
        'short_address',
        'submitted_at',
        'image_thumbnail',
        # ✅ NEW: Add bank columns to list view
        'owner_bank_name',
        'owner_account_number',
        'bank_verified_status',
        'description_preview',
        'known_issues_preview',
        'house_rules_preview',
        'signature_info',
        'is_owner_verified',
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
        # ✅ NEW: Add bank verification filter
        ('draft__bank_verified', admin.BooleanFieldListFilter),
    )

    search_fields = (
        'draft__title',
        'draft__description',
        'draft__address',
        'draft__known_issues',
        'draft__house_rules',
        'draft__user__username',
        'draft__user__email',
        'approved_by__username',
        'draft__phone_number',
        # ✅ NEW: Add bank fields to search
        'draft__owner_bank_name',
        'draft__owner_account_number',
    )

    date_hierarchy = 'draft__created_at'


    # === DETAIL VIEW FIELDSETS (CORRECTED) ===
    # Only include actual model fields or admin readonly fields that return values.
    # Do NOT include methods meant only for list_display.
    fieldsets = (
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
        ("📍 Location & Address (from Draft)", {
            "fields": (
                "full_address", # Admin readonly field showing draft.address
                "latitude",     # Admin readonly field showing draft.latitude
                "longitude"     # Admin readonly field showing draft.longitude
            ),
            "classes": ("wide",),
        }),
        ("📄 Full Details (from Draft)", {
            "fields": (
                "description", # Admin readonly field showing draft.description
                "known_issues", # Admin readonly field showing draft.known_issues
                "house_rules", # Admin readonly field showing draft.house_rules
                "image_thumbnails", # Admin readonly field showing draft.images
            ),
            "classes": ("wide",),
        }),
        ("💰 Financial Info (from Draft)", {
            "fields": (
                "formatted_monthly_rent", # Admin readonly field showing draft.monthly_rent
                "currency", # Admin readonly field showing draft.currency
                "lease_term_preference_detail", # Admin readonly field showing draft.lease_term_preference
                "phone_number_detail", # Admin readonly field showing draft.phone_number
                # ✅ NEW: Add bank details to financial info section
                "owner_bank_name_detail", # Admin readonly field showing draft.owner_bank_name
                "owner_account_number_detail", # Admin readonly field showing draft.owner_account_number
                "bank_verified_detail", # Admin readonly field showing draft.bank_verified
            ),
            "classes": ("wide",),
        }),
        # If Property model has any direct fields (not from draft), add them here.
        # Example:
        # ("Direct Property Fields", {
        #     "fields": ("direct_field1", "direct_field2"),
        #     "classes": ("wide",),
        # }),
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
        'currency', # Ensure this method exists if currency is only on draft
        'lease_term_preference_detail',
        'phone_number_detail',
        # ✅ NEW: Add bank detail readonly fields
        'owner_bank_name_detail',
        'owner_account_number_detail',
        'bank_verified_detail',
        'approved_at',
        'published_at',
        'approved_by',
        'status'
    )

    def full_address(self, obj):
        # Assuming obj.draft exists and links to PropertyDraft
        if not obj.draft:
            return "❌ Draft Missing"
        return obj.draft.address or "-"

    def latitude(self, obj):
        if not obj.draft:
            return None
        return obj.draft.latitude

    def longitude(self, obj):
        if not obj.draft:
            return None
        return obj.draft.longitude

    def description(self, obj):
        if not obj.draft:
            return "❌ Draft Missing"
        return obj.draft.description or "No description provided."

    def known_issues(self, obj):
        if not obj.draft:
            return "❌ Draft Missing"
        return obj.draft.known_issues or "No known issues reported."

    def house_rules(self, obj):
        if not obj.draft:
            return "❌ Draft Missing"
        return obj.draft.house_rules or "No house rules specified."

    def image_thumbnails(self, obj):
        if not obj.draft:
            return "❌ Draft Missing"
        if not obj.draft.images:
            return "No images uploaded."
        html = "<div style='display: flex; gap: 10px; flex-wrap: wrap;'>"
        for url in obj.draft.images:
            html += f"<img src='{url}' style='width: 150px; height: 120px; object-fit: cover; border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);' />"
        html += "</div>"
        return mark_safe(html)
    image_thumbnails.short_description = "Image Gallery"

    def formatted_monthly_rent(self, obj):
        if not obj.draft or obj.draft.monthly_rent is None:
            return "❌ Rent Missing"
        return f"₦{obj.draft.monthly_rent:,.0f}"

    def currency(self, obj): # If currency is only on draft, you need this method
        if not obj.draft:
            return "—"
        return obj.draft.currency

    def lease_term_preference_detail(self, obj):
        if not obj.draft:
            return "—"
        return obj.draft.lease_term_preference.replace('_', ' ').title()

    def phone_number_detail(self, obj):
        if not obj.draft:
            return "—"
        return obj.draft.phone_number

    # ✅ NEW: Bank Detail Readonly Fields for Detail View
    def owner_bank_name_detail(self, obj):
        if not obj.draft:
            return "—"
        return obj.draft.owner_bank_name or "—"

    def owner_account_number_detail(self, obj):
        if not obj.draft:
            return "—"
        return obj.draft.owner_account_number or "—"

    def bank_verified_detail(self, obj):
        if not obj.draft:
            return "❌ Draft Missing"
        return "✅ Yes" if obj.draft.bank_verified else "❌ No"


    # === SECURITY & UX ===
    def has_add_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('status',)
        return self.readonly_fields

    actions = ['approve_selected_listings', 'reject_selected_listings']

    def approve_selected_listings(self, request, queryset):
        updated = 0
        for prop in queryset:
            if prop.status == 'pending':
                prop.approve(request.user)
                updated += 1
        self.message_user(request, f"✅ Successfully approved {updated} listing(s).")

    approve_selected_listings.short_description = "✅ Approve selected listings"

    def reject_selected_listings(self, request, queryset):
        updated = 0
        for prop in queryset:
            if prop.status == 'pending':
                prop.reject(request.user, reason="Not specified")
                updated += 1
        self.message_user(request, f"❌ Rejected {updated} listing(s).")

    reject_selected_listings.short_description = "❌ Reject selected listings"
