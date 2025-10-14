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