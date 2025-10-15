# agent_listings/serializers.py

from rest_framework import serializers
from .models import AgentPropertyDraft, AgentProperty


class AgentPropertyDraftSerializer(serializers.ModelSerializer):
    """
    Used for all agent listing CRUD operations.
    Excludes auto-generated timestamps.
    """
    class Meta:
        model = AgentPropertyDraft
        exclude = ['created_at', 'updated_at']


class AgentPropertyAdminSerializer(serializers.ModelSerializer):
    """
    For admin panel or internal review API.
    Includes extra context: agent name and landlord contact info.
    """
    agent_name = serializers.SerializerMethodField()
    landlord_info = serializers.SerializerMethodField()

    class Meta:
        model = AgentProperty
        fields = '__all__'

    def get_agent_name(self, obj):
        agent = obj.draft.agent
        full_name = agent.get_full_name().strip() if agent.get_full_name() else None
        return f"{full_name or agent.username} ({agent.email})"

    def get_landlord_info(self, obj):
        d = obj.draft
        name = d.landlord_name or "Not provided"
        phone = d.landlord_phone or "No phone"
        email = d.landlord_email or "No email"
        return f"{name} | {phone} | {email}"


# === PUBLIC SERIALIZERS (aligned with listings/) ===

class AgentPropertyDetailSerializer(serializers.ModelSerializer):
    """
    Public-facing serializer for approved agent-submitted property details.
    Exposes only safe, relevant fields from the draft.
    """
    # Property Info
    title = serializers.CharField(source='draft.title')
    monthly_rent = serializers.DecimalField(max_digits=12, decimal_places=2, source='draft.monthly_rent')
    currency = serializers.CharField(source='draft.currency')
    lease_term_preference = serializers.CharField(source='draft.lease_term_preference')
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

    # Landlord Info
    landlord_name = serializers.CharField(source='draft.landlord_name')
    landlord_phone = serializers.CharField(source='draft.landlord_phone')
    landlord_email = serializers.CharField(source='draft.landlord_email')

    # Metadata
    published_at = serializers.DateTimeField()

    class Meta:
        model = AgentProperty
        fields = [
            'id',
            'title',
            'monthly_rent',
            'currency',
            'lease_term_preference',
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
            'landlord_name',
            'landlord_phone',
            'landlord_email',
            'published_at',
        ]


class AgentPropertyListingSerializer(serializers.ModelSerializer):
    """
    Public serializer for listing approved agent-submitted properties (list view).
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
        model = AgentProperty
        fields = [
            'id',
            'title',
            'monthly_rent',
            'currency',
            'property_type',
            'city',
            'state',
            'images',
            'published_at',
        ]