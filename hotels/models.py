from django.db import models
from django.conf import settings  # ✅ Use settings.AUTH_USER_MODEL
from django.utils import timezone


class HotelListing(models.Model):
    PROPERTY_TYPES = [
        ('hotel', 'Hotel'),
        ('guesthouse', 'Guesthouse'),
        ('resort', 'Resort'),
        ('apartment', 'Serviced Apartment'),
        ('hostel', 'Hostel'),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # ✅ Fixed: points to your custom user
        on_delete=models.CASCADE,
        related_name='hotels'
    )
    
    # Basic Info
    name = models.CharField(max_length=255)
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPES)
    tagline = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)

    # Location
    address = models.CharField(max_length=500, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)

    # Status & Timestamps
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted for Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.get_property_type_display()})"


class HotelFeature(models.Model):
    CATEGORY_CHOICES = [
        ('general', 'General'),
        ('wellness', 'Wellness'),
        ('additional', 'Additional'),
    ]

    hotel = models.ForeignKey(HotelListing, on_delete=models.CASCADE, related_name='features')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    name = models.CharField(max_length=100)  # e.g., "Free Wi-Fi", "Swimming Pool"
    is_custom = models.BooleanField(default=False)  # True if user typed it manually

    def __str__(self):
        return f"{self.name} ({self.category})"


class RoomType(models.Model):
    hotel = models.ForeignKey(HotelListing, on_delete=models.CASCADE, related_name='room_types')
    
    name = models.CharField(max_length=100)  # e.g., "Deluxe King Room"
    max_guests = models.PositiveIntegerField()
    bed_configuration = models.CharField(max_length=255, blank=True)  # e.g., "1 King Bed, 1 Sofa Bed"
    
    # Amenities (reuse JSONField like in your current system)
    amenities = models.JSONField(default=list)  # e.g., ["TV", "Air Conditioning", "Mini Bar"]
    additional_amenities = models.TextField(blank=True)  # Custom text field
    
    price_per_night = models.DecimalField(max_digits=12, decimal_places=2)
    available_count = models.PositiveIntegerField(default=0)
    
    # Room images (list of Cloudinary URLs)
    images = models.JSONField(default=list)

    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.name} at {self.hotel.name}"