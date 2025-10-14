# listings/serializers.py

from rest_framework import serializers
from .models import PropertyDraft, Property


class PropertyDraftSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyDraft
        exclude = ['created_at', 'updated_at']  # Exclude metadata for now


class PropertyAdminSerializer(serializers.ModelSerializer):
    owner = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = '__all__'

    def get_owner(self, obj):
        return f"{obj.draft.user.get_full_name() or obj.draft.user.username}"


class PropertyDetailSerializer(serializers.ModelSerializer):
    """
    Public-facing serializer for approved property details.
    Exposes only safe, relevant fields from the draft.
    """
    title = serializers.CharField(source='draft.title')
    monthly_rent = serializers.DecimalField(max_digits=12, decimal_places=2, source='draft.monthly_rent')
    currency = serializers.CharField(source='draft.currency')
    lease_term_preference = serializers.CharField(source='draft.lease_term_preference')
    phone_number = serializers.CharField(source='draft.phone_number')
    description = serializers.CharField(source='draft.description')
    known_issues = serializers.CharField(source='draft.known_issues')
    house_rules = serializers.CharField(source='draft.house_rules')
    images = serializers.JSONField(source='draft.images')
    property_type = serializers.CharField(source='draft.property_type')
    
    # Location
    address = serializers.CharField(source='draft.address')
    latitude = serializers.FloatField(source='draft.latitude')
    longitude = serializers.FloatField(source='draft.longitude')
    city = serializers.CharField(source='draft.city')
    state = serializers.CharField(source='draft.state')

    # Metadata
    published_at = serializers.DateTimeField()

    class Meta:
        model = Property
        fields = [
            'id',
            'title',
            'monthly_rent',
            'currency',
            'lease_term_preference',
            'phone_number',
            'description',
            'known_issues',
            'house_rules',
            'images',
            'property_type',
            'address',
            'latitude',
            'longitude',
            'city',
            'state',
            'published_at',
        ]


class PropertyListingSerializer(serializers.ModelSerializer):
    """
    Public serializer for listing approved properties (list view).
    Includes only essential fields for browsing.
    """
    title = serializers.CharField(source='draft.title')
    monthly_rent = serializers.DecimalField(max_digits=12, decimal_places=2, source='draft.monthly_rent')
    currency = serializers.CharField(source='draft.currency')
    property_type = serializers.CharField(source='draft.property_type')
    city = serializers.CharField(source='draft.city')
    state = serializers.CharField(source='draft.state')
    images = serializers.JSONField(source='draft.images')
    published_at = serializers.DateTimeField()

    class Meta:
        model = Property
        fields = [
            'id', 'title', 'monthly_rent', 'currency',
            'property_type', 'city', 'state', 'images', 'published_at'
        ]