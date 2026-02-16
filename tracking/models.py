import uuid

from django.db import models
from django.utils import timezone

from agencies.models import Agency, Vehicle
from billing.models import Contract
from clients.models import ClientAccount
from core.models import User


class TrackingQuerySet(models.QuerySet):
    def for_agency(self, agency):
        return self.filter(agency=agency)


class VehicleTrackingSession(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("finished", "Terminée"),
        ("interrupted", "Interrompue"),
    ]

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="tracking_sessions")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="tracking_sessions")
    contract = models.ForeignKey(Contract, on_delete=models.SET_NULL, null=True, blank=True, related_name="tracking_sessions")
    client = models.ForeignKey(ClientAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name="tracking_sessions")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    last_lat = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    last_lng = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    last_speed = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    last_heading = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    last_accuracy = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    last_signal_at = models.DateTimeField(null=True, blank=True)

    risk_score = models.PositiveSmallIntegerField(default=0)
    max_speed = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    distance_km = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    signals_count = models.PositiveIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(default=0)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_tracking_sessions")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TrackingQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["agency", "vehicle"]),
            models.Index(fields=["agency", "contract"]),
            models.Index(fields=["agency", "client"]),
        ]
        ordering = ["-started_at"]

    def mark_signal(self, lat, lng, speed, heading, accuracy, recorded_at=None):
        recorded_at = recorded_at or timezone.now()
        self.last_lat = lat
        self.last_lng = lng
        self.last_speed = speed
        self.last_heading = heading
        self.last_accuracy = accuracy
        self.last_signal_at = recorded_at
        self.signals_count = models.F('signals_count') + 1
        if speed and speed > self.max_speed:
            self.max_speed = speed
        # distance/duration update to be handled elsewhere
        self.save(update_fields=[
            "last_lat", "last_lng", "last_speed", "last_heading", "last_accuracy", "last_signal_at", "signals_count", "max_speed"
        ])

    @property
    def is_connected(self):
        if not self.last_signal_at:
            return False
        return (timezone.now() - self.last_signal_at).total_seconds() < 25


class VehicleLocationLog(models.Model):
    EVENT_CHOICES = [
        ("normal", "Normal"),
        ("overspeed", "Excès de vitesse"),
        ("harsh_brake", "Freinage brusque"),
        ("harsh_accel", "Accélération brusque"),
        ("geofence_exit", "Sortie de zone"),
        ("geofence_enter", "Entrée en zone"),
        ("stop_suspicious", "Arrêt suspect"),
    ]

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    session = models.ForeignKey(VehicleTrackingSession, on_delete=models.CASCADE, related_name="location_logs")
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="location_logs")
    recorded_at = models.DateTimeField()
    lat = models.DecimalField(max_digits=10, decimal_places=7)
    lng = models.DecimalField(max_digits=10, decimal_places=7)
    speed = models.DecimalField(max_digits=6, decimal_places=2)
    heading = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    accuracy = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES, default="normal")
    payload = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["agency", "recorded_at"]),
            models.Index(fields=["session", "recorded_at"]),
        ]
        ordering = ["recorded_at"]


class DrivingConsent(models.Model):
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="driving_consents")
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, null=True, blank=True, related_name="driving_consents")
    client = models.ForeignKey(ClientAccount, on_delete=models.CASCADE, null=True, blank=True, related_name="driving_consents")
    consent_given = models.BooleanField(default=False)
    consented_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_info = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        unique_together = [("agency", "contract", "client")]
        indexes = [models.Index(fields=["agency", "consent_given"])]

    def give_consent(self, ip=None, device_info=None):
        self.consent_given = True
        self.consented_at = timezone.now()
        if ip:
            self.ip_address = ip
        if device_info:
            self.device_info = device_info
        self.save(update_fields=["consent_given", "consented_at", "ip_address", "device_info"])
