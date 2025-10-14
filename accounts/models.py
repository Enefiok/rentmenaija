# accounts/models.py
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    # Override default fields to ensure they're present with correct constraints
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    email = models.EmailField(unique=True)
    city = models.CharField(max_length=50)
    state = models.CharField(max_length=50)

    # Email verification
    is_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=64, blank=True, null=True, unique=True)

    # Use email as the unique identifier for login
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name', 'city', 'state']  # ← 'username' removed

    def __str__(self):
        return self.email

    def generate_verification_token(self):
        """
        Generate a secure, unique UUID4-based token and save it.
        Ensures no other user has this token.
        """
        token = str(uuid.uuid4())
        while User.objects.filter(verification_token=token).exists():
            token = str(uuid.uuid4())  # Regenerate if collision (very rare but safe)
        self.verification_token = token
        self.save(update_fields=['verification_token'])  # Only update this field
        return token