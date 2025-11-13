# hotels/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import HotelListing, HotelFeature, RoomType


class HotelFeatureInline(admin.TabularInline):
    model = HotelFeature
    extra = 0
    fields = ('category', 'name', 'is_custom')
    readonly_fields = ('category', 'name', 'is_custom')


class RoomTypeInline(admin.TabularInline):
    model = RoomType
    extra = 0
    fields = ('name', 'max_guests', 'price_per_night', 'available_count', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(HotelListing)
class HotelListingAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'property_type', 'city', 'state', 'status_badge',
        'owner_email',
        # --- NEW: Bank Details Columns ---
        'bank_name',          # Added
        'account_number',     # Added
        'bank_verified_status', # Added
        # --- END NEW ---
        'created_at', 'published_at'
    )
    list_filter = (
        'status', 'property_type', 'city', 'state', 'created_at',
        # ✅ NEW: Add bank verification filter
        'bank_verified', # Filter by bank verification status on HotelListing
    )
    search_fields = (
        'name', 'address', 'owner__email',
        # ✅ NEW: Add bank fields to search
        'owner_bank_name', 'owner_account_number'
    )
    readonly_fields = (
        'created_at', 'updated_at', 'published_at',
        'owner', 'is_owner_or_representative', 'details_accurate',
        'assume_responsibility_for_fraud', 'agrees_to_escrow_process',
        'digital_signature', 'signed_at',
        # ✅ NEW: Add bank detail readonly fields
        'owner_bank_name', 'owner_account_number', 'owner_account_name', 'bank_verified',
    )
    # ✅ NEW: Add bank verification actions for drafts
    actions = ['approve_listings', 'reject_listings', 'verify_bank_selected', 'unverify_bank_selected']
    fieldsets = (
        ('Owner & Status', {
            'fields': ('owner', 'status', 'published_at')
        }),
        ('Basic Info', {
            'fields': ('name', 'property_type', 'tagline', 'description', 'phone')
        }),
        ('📍 Location', {
            'fields': ('address', 'city', 'state', 'latitude', 'longitude')
        }),
        ('💳 Bank Account Details', { # NEW: Add bank details fieldset
            'fields': ('owner_bank_name', 'owner_account_number', 'owner_account_name', 'bank_verified'),
            'classes': ('collapse',) # Collapse by default to keep interface clean
        }),
        ('✅ Legal Declarations', {
            'fields': (
                'is_owner_or_representative',
                'details_accurate',
                'assume_responsibility_for_fraud',
                'agrees_to_escrow_process',
                'digital_signature',
                'signed_at'
            ),
            'classes': ('collapse',)
        }),
        ('📅 Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    inlines = [HotelFeatureInline, RoomTypeInline]

    # --- NEW: Bank Details Columns for List View ---
    def bank_name(self, obj):
        name = obj.owner_bank_name
        return name or "-" # Return "-" if no value
    bank_name.short_description = "Bank Name"

    def account_number(self, obj):
        number = obj.owner_account_number
        return number or "-" # Return "-" if no value
    account_number.short_description = "Account Number"

    def bank_verified_status(self, obj):
        verified = obj.bank_verified
        return format_html("✅ Yes") if verified else format_html("❌ No")
    bank_verified_status.short_description = "Bank Verified?"
    # --- END NEW ---

    def owner_email(self, obj):
        return obj.owner.email
    owner_email.short_description = "Owner"
    owner_email.admin_order_field = 'owner__email'

    def status_badge(self, obj):
        badges = {
            'draft': '<span style="color: orange;">🟡 Draft</span>',
            'submitted': '<span style="color: blue;">🔵 Submitted</span>',
            'approved': '<span style="color: green;">✅ Approved</span>',
            'rejected': '<span style="color: red;">❌ Rejected</span>',
        }
        return format_html(badges.get(obj.status, obj.status))
    status_badge.short_description = "Status"
    status_badge.admin_order_field = 'status'

    # ✅ NEW: Bank verification actions for drafts
    def verify_bank_selected(self, request, queryset):
        updated = queryset.update(bank_verified=True)
        self.message_user(request, f"✅ Bank verification set to True for {updated} draft(s).")
    verify_bank_selected.short_description = "✅ Verify Bank for selected drafts"

    def unverify_bank_selected(self, request, queryset):
        updated = queryset.update(bank_verified=False)
        self.message_user(request, f"❌ Bank verification set to False for {updated} draft(s).")
    unverify_bank_selected.short_description = "❌ Unverify Bank for selected drafts"

    def approve_listings(self, request, queryset):
        approved = 0
        for hotel in queryset:
            if hotel.status == 'submitted':
                hotel.status = 'approved'
                hotel.published_at = timezone.now()
                hotel.save(update_fields=['status', 'published_at'])
                approved += 1
        self.message_user(request, f"✅ Approved {approved} hotel listing(s).")
    approve_listings.short_description = "✅ Approve selected listings"

    def reject_listings(self, request, queryset):
        rejected = 0
        for hotel in queryset:
            if hotel.status == 'submitted':
                hotel.status = 'rejected'
                hotel.save(update_fields=['status'])
                rejected += 1
        self.message_user(request, f"❌ Rejected {rejected} hotel listing(s).")
    reject_listings.short_description = "❌ Reject selected listings"

    def get_readonly_fields(self, request, obj=None):
        # Prevent editing once approved or rejected
        if obj and obj.status in ['approved', 'rejected']:
            return self.readonly_fields + ('status',)
        return self.readonly_fields


@admin.register(HotelFeature)
class HotelFeatureAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'hotel', 'is_custom')
    list_filter = ('category', 'is_custom', 'hotel__name')
    search_fields = ('name', 'hotel__name')


@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'hotel', 'max_guests', 'price_per_night', 'available_count')
    list_filter = ('hotel__name', 'max_guests')
    search_fields = ('name', 'hotel__name')
    readonly_fields = ('created_at',)