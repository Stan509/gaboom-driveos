import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0002_add_contract_notes_cancelled'),
        ('agencies', '0024_vehicle_allow_negotiation'),
        ('clients', '0006_negotiationmessage'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Contract: new status choices ──
        migrations.AlterField(
            model_name='contract',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Brouillon'),
                    ('pending_signature', 'En attente de signature'),
                    ('active', 'Actif'),
                    ('pending_return', 'Retour en cours'),
                    ('closed', 'Clôturé'),
                    ('cancelled', 'Annulé'),
                ],
                default='draft', max_length=20,
            ),
        ),

        # ── Contract: new FK fields ──
        migrations.AddField(
            model_name='contract',
            name='client_account',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='contracts', to='clients.clientaccount',
            ),
        ),
        migrations.AddField(
            model_name='contract',
            name='reservation',
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='contract', to='agencies.reservationrequest',
            ),
        ),

        # ── Contract: datetime fields ──
        migrations.AddField(
            model_name='contract',
            name='pickup_datetime',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='contract',
            name='return_datetime',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='contract',
            name='actual_return_datetime',
            field=models.DateTimeField(blank=True, null=True),
        ),

        # ── Contract: clause fields ──
        migrations.AddField(
            model_name='contract',
            name='contract_clause',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='contract',
            name='penalty_clause',
            field=models.TextField(blank=True, default=''),
        ),

        # ── Contract: signature fields ──
        migrations.AddField(
            model_name='contract',
            name='client_signature',
            field=models.ImageField(blank=True, null=True, upload_to='contracts/signatures/'),
        ),
        migrations.AddField(
            model_name='contract',
            name='client_signed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='contract',
            name='client_signed_ip',
            field=models.GenericIPAddressField(blank=True, null=True),
        ),

        # ── VehicleStatePhoto model ──
        migrations.CreateModel(
            name='VehicleStatePhoto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('moment', models.CharField(choices=[('pickup', 'Départ'), ('return', 'Retour')], max_length=10)),
                ('photo', models.ImageField(upload_to='contracts/vehicle_state/')),
                ('description', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('contract', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='vehicle_photos', to='billing.contract',
                )),
            ],
            options={
                'ordering': ['moment', 'created_at'],
            },
        ),

        # ── VehicleReturnInspection model ──
        migrations.CreateModel(
            name='VehicleReturnInspection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('inspected_at', models.DateTimeField(auto_now_add=True)),
                ('exterior_condition', models.CharField(choices=[('excellent', 'Excellent'), ('good', 'Bon'), ('fair', 'Acceptable'), ('damaged', 'Endommagé')], default='good', max_length=20)),
                ('interior_condition', models.CharField(choices=[('excellent', 'Excellent'), ('good', 'Bon'), ('fair', 'Acceptable'), ('damaged', 'Endommagé')], default='good', max_length=20)),
                ('tires_condition', models.CharField(choices=[('excellent', 'Excellent'), ('good', 'Bon'), ('fair', 'Acceptable'), ('damaged', 'Endommagé')], default='good', max_length=20)),
                ('lights_condition', models.CharField(choices=[('excellent', 'Excellent'), ('good', 'Bon'), ('fair', 'Acceptable'), ('damaged', 'Endommagé')], default='good', max_length=20)),
                ('engine_condition', models.CharField(choices=[('excellent', 'Excellent'), ('good', 'Bon'), ('fair', 'Acceptable'), ('damaged', 'Endommagé')], default='good', max_length=20)),
                ('has_new_damage', models.BooleanField(default=False)),
                ('damage_description', models.TextField(blank=True, default='')),
                ('damage_cost_estimate', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('cleanliness_ok', models.BooleanField(default=True)),
                ('notes', models.TextField(blank=True, default='')),
                ('decision', models.CharField(choices=[('available', 'Disponible immédiatement'), ('maintenance', 'Envoyer en maintenance')], default='available', max_length=20)),
                ('contract', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='return_inspection', to='billing.contract',
                )),
                ('inspected_by', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Inspection retour',
            },
        ),
    ]
