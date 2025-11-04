import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        # Generate base username from email local part
        base_username = email.split('@')[0]
        username = base_username
        counter = 1
        while self.model.objects.filter(username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1
        extra_fields.setdefault('username', username)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    # Remove inherited username and redefine it as auto-filled
    username = models.CharField(max_length=150, unique=True, blank=True)
    email = models.EmailField(unique=True)
    city = models.CharField(max_length=50)
    state = models.CharField(max_length=50)

    # NEW: Phone number for Youverify & profile
    phone = models.CharField(max_length=15, blank=True)

    # Email verification
    is_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=64, blank=True, null=True, unique=True)

    # Identity verification via Youverify (already added earlier)
    is_identity_verified = models.BooleanField(default=False)
    identity_verification_reference = models.CharField(max_length=255, blank=True, null=True)
    identity_verified_at = models.DateTimeField(blank=True, null=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name', 'city', 'state']

    objects = UserManager()

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        # Only auto-generate username if it's not set AND we have an email
        if not self.username and self.email:
            base = self.email.split('@')[0]
            self.username = base
            counter = 1
            while User.objects.filter(username=self.username).exists():
                self.username = f"{base}_{counter}"
                counter += 1
        super().save(*args, **kwargs)

    def generate_verification_token(self):
        token = str(uuid.uuid4())
        while User.objects.filter(verification_token=token).exists():
            token = str(uuid.uuid4())
        self.verification_token = token
        self.save(update_fields=['verification_token'])
        return token