"""Сотрудники салона (мастера, администраторы). Колонки журнала = активные мастера."""
from django.db import models

from core.managers import TenantModel


class Employee(TenantModel):
    full_name = models.CharField("Имя", max_length=150)
    # Специализация — свободным текстом (парикмахер, мастер маникюра, массажист)
    specialization = models.CharField("Специализация", max_length=150, blank=True)
    # Телефон мастера (для связи/записи), опционально
    phone = models.CharField("Телефон", max_length=32, blank=True)
    # Цвет колонки/блоков в журнале (hex). Помогает различать мастеров визуально.
    color = models.CharField("Цвет", max_length=7, blank=True, default="#0071E3")
    # График: рабочие дни недели (0=Пн … 6=Вс). Пусто = график не задан (считаем,
    # что работает каждый день). По нему делим список на «в смене сегодня»/«не в смене».
    work_days = models.JSONField("Рабочие дни", default=list, blank=True)
    # Работает ли сейчас (False = уволен; уволенные не показываются в журнале)
    is_active = models.BooleanField("Работает", default=True)
    # Необязательная привязка к учётной записи (если мастер заходит в систему)
    user = models.ForeignKey(
        "core.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="employee_profiles", verbose_name="Учётная запись",
    )
    # Порядок в журнале
    sort_order = models.IntegerField("Порядок", default=100)

    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"
        ordering = ["sort_order", "full_name"]

    def __str__(self):
        return self.full_name

    def on_shift(self, day):
        """В смене ли в указанный день. Пустой график = работает каждый день."""
        if not self.is_active:
            return False
        if not self.work_days:
            return True
        return day.weekday() in self.work_days
