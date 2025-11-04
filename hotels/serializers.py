from rest_framework import serializers
from django.conf import settings
from .models import HotelListing, HotelFeature, RoomType


class HotelFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = HotelFeature
        fields = ['category', 'name', 'is_custom']


class RoomTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomType
        fields = [
            'id',
            'name',
            'max_guests',
            'bed_configuration',
            'amenities',
            'additional_amenities',
            'price_per_night',
            'available_count',
            'images',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class HotelListingSerializer(serializers.ModelSerializer):
    features = HotelFeatureSerializer(many=True, required=False)
    room_types = RoomTypeSerializer(many=True, required=False)

    class Meta:
        model = HotelListing
        fields = [
            'id',
            'name',
            'property_type',
            'tagline',
            'description',
            'phone',
            'address',
            'latitude',
            'longitude',
            'city',
            'state',
            'status',
            'features',
            'room_types',
            'created_at',
            'updated_at',
            'published_at',
            # Legal declaration fields (from UI)
            'is_owner_or_representative',
            'details_accurate',
            'assume_responsibility_for_fraud',
            'agrees_to_escrow_process',
            'digital_signature',
            'signed_at',
            # Hotel-level images (exterior, lobby, pool, etc.)
            'images'  # ✅ Added
        ]
        read_only_fields = [
            'id', 'status', 'created_at', 'updated_at', 'published_at',
            'latitude', 'longitude', 'city', 'state',
            'signed_at',
            'images'  # ✅ Optional: make read-only if frontend only uploads via dedicated endpoint
        ]

    def create(self, validated_data):
        features_data = validated_data.pop('features', [])
        room_types_data = validated_data.pop('room_types', [])
        hotel = HotelListing.objects.create(**validated_data)

        # Create features
        for feature_data in features_data:
            HotelFeature.objects.create(hotel=hotel, **feature_data)

        # Create room types
        for room_data in room_types_data:
            RoomType.objects.create(hotel=hotel, **room_data)

        return hotel

    def update(self, instance, validated_data):
        features_data = validated_data.pop('features', None)
        room_types_data = validated_data.pop('room_types', None)

        # Update hotel fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update features (full replace if provided)
        if features_data is not None:
            instance.features.all().delete()
            for feature_data in features_data:
                HotelFeature.objects.create(hotel=instance, **feature_data)

        # Update room types (full replace if provided)
        if room_types_data is not None:
            instance.room_types.all().delete()
            for room_data in room_types_data:
                RoomType.objects.create(hotel=instance, **room_data)

        return instance