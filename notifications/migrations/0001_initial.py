import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import notifications.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_initial"),
        ("appointments", "0005_appointment_source"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("auto_enabled", models.BooleanField(default=False, verbose_name="Авто-отправка")),
                ("hours_before", models.PositiveIntegerField(default=24, verbose_name="За сколько часов напоминать")),
                ("channel", models.CharField(choices=[("console", "Лог (заглушка)"), ("telegram", "Telegram"), ("sms", "SMS"), ("email", "Email")], default="console", max_length=20, verbose_name="Канал")),
                ("template", models.TextField(default=notifications.models.DEFAULT_TEMPLATE, verbose_name="Шаблон сообщения")),
                ("telegram_bot_token", models.CharField(blank=True, max_length=120, verbose_name="Токен Telegram-бота")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, related_name="%(class)ss", to="core.tenant", verbose_name="Тенант")),
            ],
            options={"verbose_name": "Настройки уведомлений", "verbose_name_plural": "Настройки уведомлений"},
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("reminder", "Напоминание о визите")], default="reminder", max_length=20, verbose_name="Тип")),
                ("channel", models.CharField(blank=True, max_length=20, verbose_name="Канал")),
                ("to", models.CharField(blank=True, max_length=120, verbose_name="Получатель")),
                ("text", models.TextField(blank=True, verbose_name="Текст")),
                ("status", models.CharField(choices=[("pending", "В очереди"), ("sent", "Отправлено"), ("failed", "Ошибка"), ("skipped", "Пропущено")], default="pending", max_length=20, verbose_name="Статус")),
                ("is_auto", models.BooleanField(default=False, verbose_name="Авто")),
                ("sent_at", models.DateTimeField(blank=True, null=True, verbose_name="Отправлено в")),
                ("error", models.CharField(blank=True, max_length=300, verbose_name="Ошибка")),
                ("external_id", models.CharField(blank=True, max_length=100, verbose_name="ID во внешней системе")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("appointment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="appointments.appointment", verbose_name="Запись")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notifications", to=settings.AUTH_USER_MODEL, verbose_name="Отправил")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, related_name="%(class)ss", to="core.tenant", verbose_name="Тенант")),
            ],
            options={"verbose_name": "Уведомление", "verbose_name_plural": "Уведомления", "ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(fields=("appointment", "kind"), name="uniq_notification_per_appt_kind"),
        ),
    ]
