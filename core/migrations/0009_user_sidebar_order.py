from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_tenant_yandex"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="sidebar_order",
            field=models.JSONField(blank=True, default=list, verbose_name="Порядок меню"),
        ),
    ]
