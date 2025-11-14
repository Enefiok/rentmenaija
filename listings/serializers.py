# listings/serializers.py

from rest_framework import serializers
from decimal import Decimal
from .models import PropertyDraft, Property


class PropertyDraftSerializer(serializers.ModelSerializer):
    # Explicitly define fields to handle type conversion from strings
    monthly_rent = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    phone_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    owner_account_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    class Meta:
        model = PropertyDraft
        exclude = ['created_at', 'updated_at']

    def validate_monthly_rent(self, value):
        """Convert string to Decimal for monthly_rent"""
        if value is None or value == '' or value == 'null':
            return None
        try:
            return Decimal(str(value))
        except (ValueError, TypeError):
            raise serializers.ValidationError("monthly_rent must be a valid number")

    def validate_phone_number(self, value):
        """Ensure phone_number is stored as string"""
        if value is None or value == '':
            return None
        return str(value)

    def validate_owner_account_number(self, value):
        """Ensure owner_account_number is stored as string"""
        if value is None or value == '':
            return None
        return str(value)

    def to_internal_value(self, data):
        """Handle conversion of string values to appropriate types before saving"""
        # Make a copy to avoid modifying original data
        data = data.copy()
        
        # Convert monthly_rent to Decimal if it's provided as string
        if 'monthly_rent' in data and data['monthly_rent'] not in (None, '', 'null'):
            try:
                monthly_rent_val = data['monthly_rent']
                if monthly_rent_val is not None:
                    data['monthly_rent'] = str(monthly_rent_val)
            except (ValueError, TypeError):
                pass
        
        return super().to_internal_value(data)


class PropertyAdminSerializer(serializers.ModelSerializer):
    owner = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = '__all__' # This will now include the new bank fields

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

    # ✅ NEW: Bank Info (Only expose bank name and verification status, not account details)
    owner_bank_name = serializers.CharField(source='draft.owner_bank_name', read_only=True)
    bank_verified = serializers.BooleanField(source='draft.bank_verified', read_only=True)

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
            # ✅ NEW: Include bank fields
            'owner_bank_name',
            'bank_verified',
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
    
    # ✅ NEW: Bank Info for list view (only bank name and verification status)
    owner_bank_name = serializers.CharField(source='draft.owner_bank_name', read_only=True)
    bank_verified = serializers.BooleanField(source='draft.bank_verified', read_only=True)
    
    published_at = serializers.DateTimeField()

    class Meta:
        model = Property
        fields = [
            'id', 'title', 'monthly_rent', 'currency',
            'property_type', 'city', 'state', 'images',
            # ✅ NEW: Include bank fields
            'owner_bank_name',
            'bank_verified',
            'published_at'
        ]