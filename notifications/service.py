"""
Бизнес-логика напоминаний — общий движок для обеих механик:
  • ручная отправка (администратор жмёт «Напомнить»);
  • авто-отправка (команда send_due_reminders по расписанию cron).

Работает в текущем tenant_context. Отправка идемпотентна: одно напоминание на
запись (уникальность appointment+kind на уровне БД), повтор не уходит.
"""
from datetime import timedelta

from django.utils import timezone

from appointments.models import Appointment
from notifications.drivers import get_driver
from notifications.models import Notification, NotificationSettings


class _SafeDict(dict):
    # Неизвестный плейсхолдер в шаблоне оставляем как есть, а не роняем .format
    def __missing__(self, key):
        return "{" + key + "}"


def get_settings():
    s = NotificationSettings.objects.first()
    if s is None:
        s = NotificationSettings.objects.create()
    return s


def due_appointments(now=None, hours_before=None):
    """Записи, которым ПОРА напомнить: статус ожидание/подтвердил, визит впереди в
    окне hours_before, и напоминание ещё не отправлено."""
    now = now or timezone.now()
    if hours_before is None:
        hours_before = get_settings().hours_before
    window_end = now + timedelta(hours=hours_before)
    sent_ids = (Notification.objects
                .filter(kind=Notification.KIND_REMINDER, status=Notification.ST_SENT)
                .values_list("appointment_id", flat=True))
    return (Appointment.objects
            .filter(status__in=[Appointment.STATUS_WAIT, Appointment.STATUS_CONFIRMED],
                    start__gt=now, start__lte=window_end)
            .exclude(id__in=sent_ids)
            .select_related("client", "employee", "service")
            .order_by("start"))


def build_text(settings, appt):
    local = timezone.localtime(appt.start)
    values = _SafeDict(
        client=appt.client.full_name if appt.client_id else "",
        salon=appt.tenant.brand_name or appt.tenant.name,
        date=local.strftime("%d.%m"),
        time=local.strftime("%H:%M"),
        service=appt.service.name if appt.service_id else "",
        master=appt.employee.full_name if appt.employee_id else "",
    )
    return (settings.template or "").format_map(values)


def send_reminder(appt, by_user=None, is_auto=False, settings=None):
    """Отправляет напоминание по записи. Идемпотентно: если уже отправлено — вернёт
    существующее уведомление и ничего не шлёт повторно."""
    settings = settings or get_settings()
    notif, _created = Notification.objects.get_or_create(
        appointment=appt, kind=Notification.KIND_REMINDER,
        defaults={"channel": settings.channel},
    )
    if notif.status == Notification.ST_SENT:
        return notif

    to = (getattr(appt.client, "phone", "") if appt.client_id else "") or ""
    text = build_text(settings, appt)
    res = get_driver(settings).send(to, text)

    notif.channel = settings.channel
    notif.to = to
    notif.text = text
    notif.is_auto = is_auto
    notif.created_by = by_user
    if res.get("ok"):
        notif.status = Notification.ST_SENT
        notif.sent_at = timezone.now()
        notif.external_id = res.get("external_id", "")
        notif.error = ""
    else:
        notif.status = Notification.ST_FAILED
        notif.error = (res.get("error", "") or "")[:300]
    notif.save()
    return notif


def process_tenant_auto(now=None):
    """Авто-режим для текущего тенанта: шлёт напоминания всем, кому пора. Возвращает
    число успешно отправленных."""
    settings = get_settings()
    if not settings.auto_enabled:
        return 0
    sent = 0
    for appt in due_appointments(now, settings.hours_before):
        n = send_reminder(appt, is_auto=True, settings=settings)
        if n.status == Notification.ST_SENT:
            sent += 1
    return sent
