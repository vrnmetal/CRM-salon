"""Клиенты салона. Телефон уникален в пределах тенанта — основа дедупликации."""
from django.db import models

from core.managers import TenantModel


class Client(TenantModel):
    full_name = models.CharField("Имя", max_length=150)
    # Телефон — ключ дедупликации (get_or_create по телефону в пределах тенанта)
    phone = models.CharField("Телефон", max_length=32, db_index=True)
    email = models.EmailField("Email", blank=True)
    note = models.CharField("Заметка", max_length=300, blank=True)
    # Telegram chat_id — заполняется, когда клиент подписался на бота салона
    # (через /start + «поделиться контактом»). Нужен для напоминаний в Telegram.
    telegram_chat_id = models.CharField("Telegram chat_id", max_length=40, blank=True, default="")
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"
        ordering = ["full_name"]
        # Один телефон = один клиент в салоне (против дублей — наш клин «чистота данных»)
        constraints = [
            models.UniqueConstraint(fields=["tenant", "phone"], name="uniq_tenant_phone")
        ]

    def __str__(self):
        return self.full_name or self.phone
