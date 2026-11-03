from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0004_appointmentservice"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="source",
            field=models.CharField(
                choices=[
                    ("journal", "Журнал"),
                    ("portal", "Онлайн-портал"),
                    ("external", "Внешняя площадка"),
                ],
                default="journal",
                max_length=20,
                verbose_name="Источник",
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="external_system",
            field=models.CharField(
                blank=True, default="", max_length=30, verbose_name="Внешняя система"
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="external_id",
            field=models.CharField(
                blank=True, db_index=True, default="", max_length=120, verbose_name="Внешний ID"
            ),
        ),
    ]
