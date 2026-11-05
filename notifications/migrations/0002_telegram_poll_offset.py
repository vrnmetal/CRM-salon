from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationsettings",
            name="telegram_poll_offset",
            field=models.BigIntegerField(default=0, verbose_name="Telegram offset"),
        ),
    ]
