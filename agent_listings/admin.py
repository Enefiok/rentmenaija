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
    # === Enhanced List View ===
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

    # === Filters in Right Sidebar ===
    list_filter = (
        'submitted_for_review',
        'lease_term_preference',
        'currency',
        'created_at',
        'updated_at',
    )

    # === Searchable Fields ===
    search_fields = (
        'title',
        'agent__username',
        'agent__email',
        'landlord_name',
        'landlord_phone',
        'address',
        'description',
    )

    # === Read-only Fields ===
    readonly_fields = ('created_at', 'updated_at', 'signed_at')

    # === Custom Actions ===
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

    # === Custom Actions ===
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

    # === Custom Display Methods ===

    def title(self, obj):
        return obj.draft.title or "Untitled"
    title.short_description = "Title"
    title.admin_order_field = 'draft__title'

    def rent(self, obj):
        return format_currency(obj.draft.monthly_rent, obj.draft.currency)
    rent.short_description = "Monthly Rent"
    rent.admin_order_field = 'draft__monthly_rent'

    def lease_term(self, obj):
        term = obj.draft.lease_term_preference
        return term.replace('_', ' ').title() if term else "Not set"
    lease_term.short_description = "Lease Term"
    lease_term.admin_order_field = 'draft__lease_term_preference'

    def agent(self, obj):
        user = obj.draft.agent
        full_name = user.get_full_name()
        return full_name.strip() if full_name else user.username
    agent.short_description = "Listing Agent"
    agent.admin_order_field = 'draft__agent__username'

    def landlord_name(self, obj):
        return obj.draft.landlord_name
    landlord_name.short_description = "Landlord Name"
    landlord_name.admin_order_field = 'draft__landlord_name'

    def landlord_phone(self, obj):
        return obj.draft.landlord_phone
    landlord_phone.short_description = "Landlord Phone"

    def landlord_email(self, obj):
        return obj.draft.landlord_email or "—"
    landlord_email.short_description = "Landlord Email"

    def address(self, obj):
        addr = obj.draft.address
        if not addr:
            return "No address"
        query = addr.replace(' ', '+')
        return format_html(
            '<a href="https://www.google.com/maps/search/?api=1&query={}" target="_blank">{}</a>',
            query, addr
        )
    address.short_description = "Address"
    address.admin_order_field = 'draft__address'

    def location_coords(self, obj):
        lat = obj.draft.latitude
        lng = obj.draft.longitude
        if lat and lng:
            return format_html(
                '<span style="font-family: monospace;">{}, {}</span>',
                round(lat, 4), round(lng, 4)
            )
        return "—"
    location_coords.short_description = "Coordinates"

    def description_preview(self, obj):
        desc = obj.draft.description
        if not desc:
            return "—"
        return desc if len(desc) < 60 else desc[:57] + "..."
    description_preview.short_description = "Description"

    def known_issues_preview(self, obj):
        issues = obj.draft.known_issues
        if not issues:
            return "—"
        return issues if len(issues) < 60 else issues[:57] + "..."  # ✅ ADDED!
    known_issues_preview.short_description = "Known Issues"

    def house_rules_preview(self, obj):
        rules = obj.draft.house_rules
        if not rules:
            return "—"
        return rules if len(rules) < 60 else rules[:57] + "..."
    house_rules_preview.short_description = "House Rules"

    def submitted_for_review(self, obj):
        val = obj.draft.submitted_for_review
        return format_html("<strong style='color:green'>Yes</strong>") if val else "No"
    submitted_for_review.short_description = "Submitted?"
    submitted_for_review.admin_order_field = 'draft__submitted_for_review'

    def status_with_badge(self, obj):
        color_map = {'approved': 'green', 'rejected': 'red', 'pending': 'orange'}
        badge = format_html(
            '<span style="color:{}; font-weight:bold;">● {}</span>',
            color_map[obj.status], obj.get_status_display()
        )
        return badge
    status_with_badge.short_description = "Status"

    def image_thumbnail(self, obj):
        images = obj.draft.images
        if not images:
            return "❌ No Image"
        return format_html(
            '<img src="{}" style="width:60px;height:45px;object-fit:cover;border-radius:4px;" />',
            images[0]
        )
    image_thumbnail.short_description = "Image"

    # === Final list view — includes known issues ===
    list_display = (
        'title',
        'rent',
        'lease_term',
        'agent',
        'landlord_name',
        'landlord_phone',
        'address',
        'location_coords',
        'description_preview',
        'known_issues_preview',  # ✅ Included here
        'house_rules_preview',
        'submitted_for_review',
        'status_with_badge',
        'image_thumbnail',
    )

    # === Filters ===
    list_filter = (
        'status',
        'approved_at',
        'published_at',
        ('draft__submitted_for_review', admin.BooleanFieldListFilter),
        'draft__lease_term_preference',
        'draft__currency',
        'draft__created_at',
    )

    # === Search fields ===
    search_fields = (
        'draft__title',
        'draft__agent__username',
        'draft__agent__email',
        'draft__landlord_name',
        'draft__landlord_phone',
        'draft__address',
        'draft__description',
        'draft__known_issues',
        'draft__house_rules',
    )

    # === Date hierarchy ===
    date_hierarchy = 'draft__created_at'

    # === Prevent adding/deleting ===
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # === Safe readonly fields (only real fields + defined methods) ===
    readonly_fields = (
        'draft',
        'status',
        'approved_by',
        'approved_at',
        'rejected_reason',
        'published_at',

        # Admin-defined methods (safe because they’re defined below)
        'title',
        'rent',
        'lease_term',
        'agent',
        'landlord_name',
        'landlord_phone',
        'landlord_email',
        'address',
        'location_coords',
        'description_preview',
        'known_issues_preview',
        'house_rules_preview',
        'submitted_for_review',
        'status_with_badge',
        'image_thumbnail',
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('status',)
        return self.readonly_fields

    # === Bulk Actions ===
    actions = ['approve_selected', 'reject_selected']

    def approve_selected(self, request, queryset):
        updated = 0
        for prop in queryset.filter(status='pending'):
            prop.approve(request.user)
            updated += 1
        self.message_user(request, f"✅ Approved {updated} agent-submitted listing(s).")

    approve_selected.short_description = "✅ Approve selected listings"

    def reject_selected(self, request, queryset):
        updated = 0
        for prop in queryset.filter(status='pending'):
            prop.reject(request.user)
            updated += 1
        self.message_user(request, f"❌ Rejected {updated} agent-submitted listing(s).")

    reject_selected.short_description = "❌ Reject selected listings"

    # === Detailed Fieldsets for Review ===
    fieldsets = (
        ("🏡 Listing Overview", {
            "fields": ("title", "status_with_badge", "status", "approved_by", "approved_at", "rejected_reason", "published_at")
        }),
        ("💰 Pricing & Terms", {
            "fields": ("rent", "lease_term")
        }),
        ("🧑‍💼 Agent & Landlord", {
            "fields": ("agent", "landlord_name", "landlord_phone", "landlord_email")
        }),
        ("📍 Location", {
            "fields": ("address", "location_coords")
        }),
        ("📝 Description & Rules", {
            "fields": ("description_preview", "known_issues_preview", "house_rules_preview")
        }),
        ("🖼️ Media", {
            "fields": ("image_thumbnail",)
        }),
        ("✅ Compliance", {
            "fields": ("submitted_for_review",)
        }),
    )