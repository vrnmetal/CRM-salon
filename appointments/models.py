"""
Записи и справочник услуг/ресурсов.

Услуга несёт длительность и цену (из неё автозаполняются поля записи). Ресурс —
физическое место (кресло/кушетка/мойка), чтобы позже не записывать двоих на одно.
Запись связывает клиента, мастера и услугу на конкретное время со статусом визита.
"""
from django.db import models

from core.managers import TenantModel


# --- Категория услуг (окрашивание, маникюр, массаж) ---
class ServiceCategory(TenantModel):
    name = models.CharField("Название", max_length=150)
    sort_order = models.IntegerField("Порядок", default=100)

    class Meta:
        verbose_name = "Категория услуг"
        verbose_name_plural = "Категории услуг"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


# --- Ресурс (физическое место/оборудование) ---
class Resource(TenantModel):
    name = models.CharField("Название", max_length=150)

    class Meta:
        verbose_name = "Ресурс"
        verbose_name_plural = "Ресурсы"
        ordering = ["name"]

    def __str__(self):
        return self.name


# --- Услуга ---
class Service(TenantModel):
    name = models.CharField("Название", max_length=200)
    category = models.ForeignKey(
        ServiceCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="services", verbose_name="Категория",
    )
    # Длительность и цена подставляются в запись при выборе услуги
    duration_min = models.IntegerField("Длительность, мин", default=60)
    price = models.DecimalField("Цена, ₽", max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField("Активна", default=True)
    sort_order = models.IntegerField("Порядок", default=100)

    class Meta:
        verbose_name = "Услуга"
        verbose_name_plural = "Услуги"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


# --- Запись ---
class Appointment(TenantModel):
    # Статусы визита (цветовая кодировка в журнале, кормит метрику неявок)
    STATUS_WAIT = "wait"
    STATUS_CONFIRMED = "confirmed"
    STATUS_CAME = "came"
    STATUS_NOSHOW = "noshow"
    STATUS_CHOICES = [
        (STATUS_WAIT, "Ожидание"),
        (STATUS_CONFIRMED, "Подтвердил"),
        (STATUS_CAME, "Пришёл"),
        (STATUS_NOSHOW, "Не пришёл"),
    ]

    client = models.ForeignKey(
        "clients.Client", on_delete=models.PROTECT, related_name="appointments",
        verbose_name="Клиент",
    )
    employee = models.ForeignKey(
        "staff.Employee", on_delete=models.PROTECT, related_name="appointments",
        verbose_name="Мастер",
    )
    service = models.ForeignKey(
        Service, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="appointments", verbose_name="Услуга",
    )
    # Начало визита и длительность (копируется из услуги, можно переопределить)
    start = models.DateTimeField("Начало", db_index=True)
    duration_min = models.IntegerField("Длительность, мин", default=60)
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default=STATUS_WAIT)
    # Цена визита (из услуги на момент записи)
    price = models.DecimalField("Цена, ₽", max_digits=10, decimal_places=2, default=0)
    comment = models.CharField("Комментарий", max_length=500, blank=True)
    # Согласие на обработку ПДн (152-ФЗ) — фиксируем в момент записи
    pdn_consent = models.BooleanField("Согласие на обработку ПДн", default=False)
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Запись"
        verbose_name_plural = "Записи"
        ordering = ["start"]

    def __str__(self):
        return f"{self.start:%d.%m %H:%M} · {self.client}"
