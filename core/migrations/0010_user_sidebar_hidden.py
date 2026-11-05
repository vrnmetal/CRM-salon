from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_user_sidebar_order"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="sidebar_hidden",
            field=models.JSONField(blank=True, default=list, verbose_name="Скрытые пункты меню"),
        ),
    ]
