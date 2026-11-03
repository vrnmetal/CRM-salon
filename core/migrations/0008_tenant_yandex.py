from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_user_backup_codes_user_totp_enabled_user_totp_secret"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="yandex_permalink",
            field=models.CharField(blank=True, max_length=40, verbose_name="Яндекс permalink"),
        ),
        migrations.AddField(
            model_name="tenant",
            name="address",
            field=models.CharField(blank=True, max_length=255, verbose_name="Адрес"),
        ),
        migrations.AddField(
            model_name="tenant",
            name="latitude",
            field=models.DecimalField(
                blank=True, decimal_places=6, max_digits=9, null=True, verbose_name="Широта"
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="longitude",
            field=models.DecimalField(
                blank=True, decimal_places=6, max_digits=9, null=True, verbose_name="Долгота"
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="public_phone",
            field=models.CharField(blank=True, max_length=20, verbose_name="Телефон для клиентов"),
        ),
        migrations.AddField(
            model_name="tenant",
            name="yandex_rubric",
            field=models.CharField(
                blank=True, default="Салон красоты", max_length=100, verbose_name="Рубрика (Яндекс)"
            ),
        ),
    ]
