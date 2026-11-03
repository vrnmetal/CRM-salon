"""
Абонементы и сертификаты — предоплата как драйвер выручки.

SubscriptionPlan   — продукт, который продаёт салон:
                     • VISITS — пакет на N визитов (опц. конкретной услуги);
                     • MONEY  — сертификат на сумму (баланс ₽, тратится на любую услугу).
ClientSubscription — купленный клиентом экземпляр (остаток визитов/денег, срок).
SubscriptionUsage  — лог списаний (на какую запись, сколько).
"""
from django.db import models

from core.managers import TenantModel


class SubscriptionPlan(TenantModel):
    VISITS = "visits"
    MONEY = "money"
    KIND_CHOICES = [(VISITS, "Пакет визитов"), (MONEY, "Сертификат на сумму")]

    name = models.CharField("Название", max_length=200)
    kind = models.CharField("Тип", max_length=10, choices=KIND_CHOICES, default=VISITS)
    # Для VISITS: услуга (пусто = любая) и число визитов
    service = models.ForeignKey(
        "appointments.Service", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="subscription_plans", verbose_name="Услуга (для пакета визитов)",
    )
    total_uses = models.IntegerField("Визитов в пакете", default=0)
    # Цена продажи
    price = models.DecimalField("Цена, ₽", max_digits=10, decimal_places=2, default=0)
    # Для MONEY: сколько ₽ зачисляется на баланс (>= price → бонус/выгода)
    value = models.DecimalField("Зачисляется на баланс, ₽", max_digits=10, decimal_places=2, default=0)
    validity_days = models.IntegerField("Срок действия, дней (0 = бессрочно)", default=0)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Продукт (абонемент/сертификат)"
        verbose_name_plural = "Абонементы и сертификаты"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def bonus(self):
        return (self.value or 0) - (self.price or 0) if self.kind == self.MONEY else 0


class ClientSubscription(TenantModel):
    ACTIVE = "active"
    FINISHED = "finished"
    EXPIRED = "expired"
    STATUS_CHOICES = [(ACTIVE, "Активен"), (FINISHED, "Израсходован"), (EXPIRED, "Истёк")]

    client = models.ForeignKey(
        "clients.Client", on_delete=models.CASCADE, related_name="subscriptions", verbose_name="Клиент",
    )
    plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sold", verbose_name="Продукт",
    )
    # Снимок параметров на момент продажи (продукт может измениться/удалиться)
    name = models.CharField("Название", max_length=200)
    kind = models.CharField("Тип", max_length=10, choices=SubscriptionPlan.KIND_CHOICES)
    service = models.ForeignKey(
        "appointments.Service", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="client_subscriptions", verbose_name="Услуга",
    )
    remaining_uses = models.IntegerField("Остаток визитов", default=0)
    balance = models.DecimalField("Остаток, ₽", max_digits=10, decimal_places=2, default=0)
    purchased_at = models.DateTimeField("Куплен", auto_now_add=True)
    expires_at = models.DateField("Действует до", null=True, blank=True)
    status = models.CharField("Статус", max_length=10, choices=STATUS_CHOICES, default=ACTIVE)

    class Meta:
        verbose_name = "Абонемент клиента"
        verbose_name_plural = "Абонементы клиентов"
        ordering = ["-purchased_at"]

    def __str__(self):
        return f"{self.name} · {self.client}"

    def is_valid(self, today):
        if self.status != self.ACTIVE:
            return False
        if self.expires_at and today > self.expires_at:
            return False
        if self.kind == SubscriptionPlan.VISITS:
            return self.remaining_uses > 0
        return self.balance > 0

    def covers(self, appointment):
        """Можно ли оплатить этот визит данным абонементом."""
        if self.kind == SubscriptionPlan.VISITS:
            # Пакет конкретной услуги — проверяем совпадение
            if self.service_id and self.service_id != appointment.service_id:
                return False
            return self.remaining_uses > 0
        return self.balance >= (appointment.price or 0)


class SubscriptionUsage(TenantModel):
    subscription = models.ForeignKey(
        ClientSubscription, on_delete=models.CASCADE, related_name="usages", verbose_name="Абонемент",
    )
    appointment = models.ForeignKey(
        "appointments.Appointment", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="subscription_usages", verbose_name="Запись",
    )
    uses_spent = models.IntegerField("Списано визитов", default=0)
    amount_spent = models.DecimalField("Списано, ₽", max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField("Когда", auto_now_add=True)

    class Meta:
        verbose_name = "Списание абонемента"
        verbose_name_plural = "Списания абонементов"
        ordering = ["-created_at"]
