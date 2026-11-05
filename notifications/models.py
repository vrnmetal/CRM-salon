"""
Уведомления и напоминания.

- NotificationSettings — настройки на тенанта (singleton): авто-режим, за сколько
  часов напоминать, канал, шаблон текста.
- Notification — лог/очередь одного уведомления: что, кому, каким каналом, статус.
  Уникальность (appointment, kind) делает отправку идемпотентной — одно напоминание
  на запись, второй раз не уйдёт (ни вручную, ни авто).
"""
from django.db import models

from core.managers import TenantModel

DEFAULT_TEMPLATE = (
    "Здравствуйте, {client}! Напоминаем о записи в «{salon}»: "
    "{date} в {time}, {service}. Ждём вас!"
)


class NotificationSettings(TenantModel):
    CH_CONSOLE = "console"
    CH_TELEGRAM = "telegram"
    CH_SMS = "sms"
    CH_EMAIL = "email"
    CHANNEL_CHOICES = [
        (CH_CONSOLE, "Лог (заглушка)"),
        (CH_TELEGRAM, "Telegram"),
        (CH_SMS, "SMS"),
        (CH_EMAIL, "Email"),
    ]

    auto_enabled = models.BooleanField("Авто-отправка", default=False)
    hours_before = models.PositiveIntegerField("За сколько часов напоминать", default=24)
    channel = models.CharField("Канал", max_length=20, choices=CHANNEL_CHOICES, default=CH_CONSOLE)
    template = models.TextField("Шаблон сообщения", default=DEFAULT_TEMPLATE)
    telegram_bot_token = models.CharField("Токен Telegram-бота", max_length=120, blank=True)
    # Смещение getUpdates при опросе бота (polling без вебхука) — чтобы не обрабатывать дважды
    telegram_poll_offset = models.BigIntegerField("Telegram offset", default=0)

    # --- SMS (агрегатор, модель A: у салона свой аккаунт) ---
    sms_provider = models.CharField("SMS-провайдер", max_length=20, default="smsc")
    sms_login = models.CharField("SMS логин", max_length=100, blank=True)
    sms_password = models.CharField("SMS пароль/ключ", max_length=100, blank=True)
    sms_sender = models.CharField("Имя отправителя (альфа-имя)", max_length=20, blank=True)

    class Meta:
        verbose_name = "Настройки уведомлений"
        verbose_name_plural = "Настройки уведомлений"

    def __str__(self):
        return f"Уведомления: {self.get_channel_display()}, авто={self.auto_enabled}"


class Notification(TenantModel):
    KIND_REMINDER = "reminder"
    KIND_CHOICES = [(KIND_REMINDER, "Напоминание о визите")]

    ST_PENDING = "pending"
    ST_SENT = "sent"
    ST_FAILED = "failed"
    ST_SKIPPED = "skipped"
    STATUS_CHOICES = [
        (ST_PENDING, "В очереди"),
        (ST_SENT, "Отправлено"),
        (ST_FAILED, "Ошибка"),
        (ST_SKIPPED, "Пропущено"),
    ]

    appointment = models.ForeignKey(
        "appointments.Appointment", on_delete=models.CASCADE,
        related_name="notifications", verbose_name="Запись",
    )
    kind = models.CharField("Тип", max_length=20, choices=KIND_CHOICES, default=KIND_REMINDER)
    channel = models.CharField("Канал", max_length=20, blank=True)
    to = models.CharField("Получатель", max_length=120, blank=True)  # снимок (телефон/адрес)
    text = models.TextField("Текст", blank=True)
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default=ST_PENDING)
    is_auto = models.BooleanField("Авто", default=False)
    created_by = models.ForeignKey(
        "core.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="notifications", verbose_name="Отправил",
    )
    sent_at = models.DateTimeField("Отправлено в", null=True, blank=True)
    error = models.CharField("Ошибка", max_length=300, blank=True)
    external_id = models.CharField("ID во внешней системе", max_length=100, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["appointment", "kind"], name="uniq_notification_per_appt_kind"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.get_status_display()}"
