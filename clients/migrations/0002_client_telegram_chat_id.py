from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="telegram_chat_id",
            field=models.CharField(blank=True, default="", max_length=40, verbose_name="Telegram chat_id"),
        ),
    ]
