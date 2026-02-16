from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agencies', '0023_marketingcampaign_channel_config_campaignautomation_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehicle',
            name='allow_negotiation',
            field=models.BooleanField(default=False),
        ),
    ]
