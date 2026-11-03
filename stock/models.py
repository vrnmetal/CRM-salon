"""
Склад и тех. карты.

Material      — расходник с остатком и себестоимостью единицы.
TechCardItem  — строка тех. карты: сколько материала уходит на одну услугу.
StockMovement — движение склада (приход/списание/корректировка), в т.ч. авто-списание
                при проведении визита (ссылается на запись, чтобы не списать дважды).

Себестоимость услуги = сумма (расход × цена единицы) по её тех. карте → кормит маржу.
"""
from decimal import Decimal

from django.db import models

from core.managers import TenantModel


UNIT_CHOICES = [
    ("шт", "шт"), ("мл", "мл"), ("г", "г"), ("мин", "мин"), ("усл", "усл.ед"),
]


class Material(TenantModel):
    name = models.CharField("Название", max_length=200)
    unit = models.CharField("Единица", max_length=10, choices=UNIT_CHOICES, default="шт")
    quantity = models.DecimalField("Остаток", max_digits=12, decimal_places=2, default=0)
    low_threshold = models.DecimalField("Порог «мало»", max_digits=12, decimal_places=2, default=0)
    cost_per_unit = models.DecimalField("Цена за единицу, ₽", max_digits=10, decimal_places=2, default=0)
    # Норма потерь/перерасхода, % (погрешность жидкостей, брак/поломка штучных).
    # Учитывается при авто-списании, себестоимости и расчёте «на сколько хватит».
    waste_pct = models.DecimalField("Потери, %", max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Материал"
        verbose_name_plural = "Материалы"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_low(self):
        return self.low_threshold and self.quantity <= self.low_threshold


class TechCardItem(TenantModel):
    service = models.ForeignKey(
        "appointments.Service", on_delete=models.CASCADE,
        related_name="techcard", verbose_name="Услуга",
    )
    material = models.ForeignKey(
        Material, on_delete=models.PROTECT, related_name="in_techcards", verbose_name="Материал",
    )
    qty = models.DecimalField("Расход на услугу", max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Строка тех. карты"
        verbose_name_plural = "Тех. карты"
        unique_together = [("service", "material")]

    def __str__(self):
        return f"{self.service} · {self.material} ×{self.qty}"

    @property
    def effective_qty(self):
        # Реальный расход с учётом нормы потерь материала (всё в Decimal)
        qty = self.qty or Decimal("0")
        waste = (self.material.waste_pct or Decimal("0")) / Decimal("100")
        return qty * (Decimal("1") + waste)

    @property
    def line_cost(self):
        # Себестоимость с учётом потерь (чтобы маржа была честной)
        return self.effective_qty * (self.material.cost_per_unit or 0)


class AppointmentMaterial(TenantModel):
    """Фактический расход материала на КОНКРЕТНУЮ запись (разовая корректировка).
    Если такие строки есть — списываем по ним, а не по тех. карте."""
    appointment = models.ForeignKey(
        "appointments.Appointment", on_delete=models.CASCADE,
        related_name="material_usage", verbose_name="Запись",
    )
    material = models.ForeignKey(
        Material, on_delete=models.PROTECT, related_name="appt_usage", verbose_name="Материал",
    )
    qty = models.DecimalField("Факт. расход", max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Расход по записи"
        verbose_name_plural = "Расход по записям"
        unique_together = [("appointment", "material")]

    def __str__(self):
        return f"{self.appointment_id}: {self.material} ×{self.qty}"


class StockMovement(TenantModel):
    PURCHASE = "purchase"     # приход (закупка)
    CONSUME = "consume"       # списание по услуге
    ADJUST = "adjust"         # корректировка (инвентаризация)
    REASON_CHOICES = [
        (PURCHASE, "Приход"),
        (CONSUME, "Списание (услуга)"),
        (ADJUST, "Корректировка"),
    ]

    material = models.ForeignKey(
        Material, on_delete=models.CASCADE, related_name="movements", verbose_name="Материал",
    )
    delta = models.DecimalField("Изменение", max_digits=12, decimal_places=2)
    reason = models.CharField("Причина", max_length=20, choices=REASON_CHOICES, default=ADJUST)
    appointment = models.ForeignKey(
        "appointments.Appointment", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="stock_movements", verbose_name="Запись",
    )
    note = models.CharField("Комментарий", max_length=200, blank=True)
    created_at = models.DateTimeField("Когда", auto_now_add=True)

    class Meta:
        verbose_name = "Движение склада"
        verbose_name_plural = "Движения склада"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.material} {self.delta:+}"
