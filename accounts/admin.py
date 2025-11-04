from django.contrib import admin
from django.contrib.auth import get_user_model

User = get_user_model()


@admin.register(User)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "username",
        "email",
        "first_name",
        "last_name",
        "city",
        "state",
        "is_verified",
        "is_staff",
        "is_active",
        "date_joined",
    )
    search_fields = ("username", "email", "first_name", "last_name", "city", "state")
    list_filter = ("is_verified", "is_staff", "is_active", "date_joined")
    ordering = ("-date_joined",)
