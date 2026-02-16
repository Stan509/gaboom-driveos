from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agencies', '0024_vehicle_allow_negotiation'),
    ]

    operations = [
        migrations.AddField(
            model_name='businesssettings',
            name='default_contract_clause',
            field=models.TextField(
                blank=True,
                default="Le locataire reconnaît avoir reçu le véhicule en bon état de fonctionnement "
                "à la date et heure indiquées ci-dessus. Il s'engage à le restituer dans le même état, "
                "à la date et heure convenues. Tout retard de restitution entraînera des pénalités "
                "conformément aux conditions tarifaires de l'agence. Le locataire est responsable de tout "
                "dommage causé au véhicule pendant la durée de la location.",
            ),
        ),
        migrations.AddField(
            model_name='businesssettings',
            name='default_penalty_clause',
            field=models.TextField(
                blank=True,
                default="En cas de retard de restitution, une pénalité sera appliquée par jour de retard. "
                "En cas de dommage constaté au retour, les frais de réparation seront à la charge du locataire, "
                "déduction faite de la franchise d'assurance le cas échéant.",
            ),
        ),
    ]
