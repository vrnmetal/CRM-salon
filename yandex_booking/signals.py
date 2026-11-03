"""
Сигналы обратной синхронизации с Яндексом.

Когда запись, созданную через Яндекс (external_system='yandex'), МЕНЯЮТ или
УДАЛЯЮТ внутри нашего журнала — шлём обновление в Яндекс. Изменения, пришедшие
из самого Яндекса (через наш API), оборачиваются в suppress() и сюда не
доходят, чтобы не зациклиться.
"""
import contextlib
import contextvars

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from appointments.models import Appointment
from yandex_booking.client import push_booking_update

# Флаг «изменение инициировано самим Яндексом» — такие не синхронизируем обратно.
_suppress = contextvars.ContextVar("yandex_suppress", default=False)


@contextlib.contextmanager
def suppress():
    token = _suppress.set(True)
    try:
        yield
    finally:
        _suppress.reset(token)


def _is_yandex(appt) -> bool:
    return getattr(appt, "external_system", "") == "yandex" and bool(appt.external_id)


@receiver(post_save, sender=Appointment)
def _on_change(sender, instance, created, **kwargs):
    if _suppress.get() or created or not _is_yandex(instance):
        return
    # Статус переноса/подтверждения — наилучшее соответствие [СВЕРИТЬ]
    status = "confirmed" if instance.status == Appointment.STATUS_CONFIRMED else "changed"
    push_booking_update(instance, status)


@receiver(post_delete, sender=Appointment)
def _on_delete(sender, instance, **kwargs):
    if _suppress.get() or not _is_yandex(instance):
        return
    push_booking_update(instance, "cancelled")
