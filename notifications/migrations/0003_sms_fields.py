from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0002_telegram_poll_offset"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationsettings",
            name="sms_provider",
            field=models.CharField(default="smsc", max_length=20, verbose_name="SMS-провайдер"),
        ),
        migrations.AddField(
            model_name="notificationsettings",
            name="sms_login",
            field=models.CharField(blank=True, max_length=100, verbose_name="SMS логин"),
        ),
        migrations.AddField(
            model_name="notificationsettings",
            name="sms_password",
            field=models.CharField(blank=True, max_length=100, verbose_name="SMS пароль/ключ"),
        ),
        migrations.AddField(
            model_name="notificationsettings",
            name="sms_sender",
            field=models.CharField(blank=True, max_length=20, verbose_name="Имя отправителя (альфа-имя)"),
        ),
    ]
