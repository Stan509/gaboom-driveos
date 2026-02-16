from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("agencies", "0024_vehicle_allow_negotiation"),
        ("clients", "0005_clientloyalty"),
    ]

    operations = [
        migrations.CreateModel(
            name="NegotiationMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sender", models.CharField(choices=[("client", "Client"), ("agency", "Agence")], max_length=10)),
                ("body", models.TextField(max_length=1000)),
                ("is_read", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="negotiation_messages",
                        to="agencies.reservationrequest",
                    ),
                ),
            ],
            options={
                "verbose_name": "Message de négociation",
                "verbose_name_plural": "Messages de négociation",
                "ordering": ["created_at"],
            },
        ),
    ]
