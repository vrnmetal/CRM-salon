"""
Оплаты. Платёж привязан к записи; обрабатывается драйвером провайдера
(терминал/эквайринг). Абстракция драйверов — в drivers.py, чтобы Эвотор/АТОЛ/
онлайн-эквайринг подключались как плагины без переписывания бизнес-логики.

54-ФЗ: фискальный чек обязателен. Поле fiscal_receipt_id — место под id чека от
ОФД/терминала; заполняется драйвером при реальной фискализации (сейчас пусто).
"""
from django.db import models

from core.managers import TenantModel


class Payment(TenantModel):
    # Статусы жизненного цикла платежа
    PENDING = "pending"       # создан, ещё не отправлен
    SENT = "sent"             # отправлен на терминал, ждём подтверждения
    PAID = "paid"             # оплачено (подтверждено терминалом/вебхуком)
    FAILED = "failed"         # ошибка
    CANCELED = "canceled"     # отменён
    STATUS_CHOICES = [
        (PENDING, "Создан"),
        (SENT, "Отправлен на терминал"),
        (PAID, "Оплачено"),
        (FAILED, "Ошибка"),
        (CANCELED, "Отменён"),
    ]

    METHOD_TERMINAL = "terminal"
    METHOD_CASH = "cash"
    METHOD_SUBSCRIPTION = "subscription"
    METHOD_CHOICES = [
        (METHOD_TERMINAL, "Терминал"),
        (METHOD_CASH, "Наличные"),
        (METHOD_SUBSCRIPTION, "Абонемент"),
    ]

    appointment = models.ForeignKey(
        "appointments.Appointment", on_delete=models.CASCADE,
        related_name="payments", verbose_name="Запись",
    )
    amount = models.DecimalField("Сумма, ₽", max_digits=10, decimal_places=2)
    method = models.CharField("Способ", max_length=20, choices=METHOD_CHOICES, default=METHOD_TERMINAL)
    # Код драйвера провайдера (terminal_stub / evotor / atol / …)
    provider = models.CharField("Драйвер", max_length=40, blank=True)
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default=PENDING)
    # Идентификатор операции на стороне терминала/эквайринга
    external_id = models.CharField("ID операции", max_length=100, blank=True)
    # Комиссия эквайринга по этому платежу (для оплат картой) — себестоимость продажи
    acquiring_fee = models.DecimalField("Комиссия эквайринга, ₽", max_digits=10, decimal_places=2, default=0)
    # 54-ФЗ: id фискального чека (ОФД/терминал). Заполнит драйвер при фискализации.
    fiscal_receipt_id = models.CharField("Фискальный чек", max_length=100, blank=True)
    error = models.CharField("Ошибка", max_length=300, blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Оплата"
        verbose_name_plural = "Оплаты"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.amount} ₽ · {self.get_status_display()}"

    @property
    def is_open(self):
        # Платёж «в работе» — уже отправлен, но ещё не завершён
        return self.status in (self.PENDING, self.SENT)
