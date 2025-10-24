# hotels/admin.py

from django.contrib import admin
from .models import HotelListing, HotelFeature, RoomType


class HotelFeatureInline(admin.TabularInline):
    model = HotelFeature
    extra = 1


class RoomTypeInline(admin.TabularInline):
    model = RoomType
    extra = 1
    fields = ('name', 'max_guests', 'price_per_night', 'available_count', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(HotelListing)
class HotelListingAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'property_type', 'city', 'state', 'status',
        'owner', 'created_at', 'published_at'
    )
    list_filter = ('status', 'property_type', 'city', 'state', 'created_at')
    search_fields = ('name', 'address', 'owner__email')
    readonly_fields = ('created_at', 'updated_at', 'published_at')
    inlines = [HotelFeatureInline, RoomTypeInline]
    fieldsets = (
        ('Owner & Status', {
            'fields': ('owner', 'status', 'published_at')
        }),
        ('Basic Info', {
            'fields': ('name', 'property_type', 'tagline', 'description', 'phone')
        }),
        ('Location', {
            'fields': ('address', 'city', 'state', 'latitude', 'longitude')
        }),
        ('Legal Declarations', {
            'fields': (
                'is_owner_or_representative',
                'details_accurate',
                'assume_responsibility_for_fraud',
                'agrees_to_escrow_process',
                'digital_signature',
                'signed_at'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


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