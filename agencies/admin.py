from django.contrib import admin

from .models import Agency, Vehicle


@admin.register(Agency)
class AgencyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "language", "public_enabled", "maintenance_mode", "created_at")
    search_fields = ("name", "slug")
    list_filter = ("language", "public_enabled", "maintenance_mode")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("agency", "make", "model", "plate_number", "daily_price", "status", "public_visible")
    search_fields = ("make", "model", "plate_number")
    list_filter = ("agency", "status", "public_visible")
