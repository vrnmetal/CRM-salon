"""
Расчёт зарплат — движок правил.

PayrollScheme — схема начисления: оклад за смену + прогрессивный % с выручки.
PayrollTier   — порог прогрессии: с какой выручки за период действует какой %.
                Применяется ставка самого высокого порога, не превышающего выручку
                (премия при обороте >15000 → выше %, >30000 → ещё выше).
Схема вешается на сотрудника (Employee.payroll_scheme).
"""
from django.db import models

from core.managers import TenantModel


class PayrollScheme(TenantModel):
    name = models.CharField("Название схемы", max_length=200)
    base_per_day = models.DecimalField("Оклад за смену, ₽", max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Схема ЗП"
        verbose_name_plural = "Схемы ЗП"
        ordering = ["name"]

    def __str__(self):
        return self.name


class PayrollTier(TenantModel):
    scheme = models.ForeignKey(
        PayrollScheme, on_delete=models.CASCADE, related_name="tiers", verbose_name="Схема",
    )
    min_revenue = models.DecimalField("Выручка от, ₽", max_digits=12, decimal_places=2, default=0)
    pct = models.DecimalField("% с выручки", max_digits=5, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Порог ЗП"
        verbose_name_plural = "Пороги ЗП"
        ordering = ["min_revenue"]
        unique_together = [("scheme", "min_revenue")]

    def __str__(self):
        return f"от {self.min_revenue} → {self.pct}%"
