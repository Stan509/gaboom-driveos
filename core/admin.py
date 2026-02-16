from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Gaboom DriveOS", {"fields": ("role", "use_custom_permissions", "agency")}),
    )
    list_display = ("username", "email", "role", "agency", "is_staff", "is_active")
    list_filter = ("role", "agency", "is_staff", "is_active")
