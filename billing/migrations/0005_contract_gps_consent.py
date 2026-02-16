from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0004_contract_gps_clause'),
    ]

    operations = [
        migrations.AddField(
            model_name='contract',
            name='gps_consent_signed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='contract',
            name='gps_consent_ip',
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
    ]
