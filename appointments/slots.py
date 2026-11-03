"""
Единый сервис расчёта свободных слотов.

ОДИН источник правды о занятости мастера. Им пользуются: журнал, публичный
портал онлайн-записи и (в будущем) интеграции с внешними площадками (Яндекс.Карты
и т.п.). Нельзя считать слоты в каждом месте по-своему — иначе рассинхрон и
двойные записи. Любая новая точка записи обязана спрашивать слоты отсюда.

Все функции работают в текущем tenant_context (как и модели) — вызывающий код
сам оборачивает вызов в нужный контекст тенанта.
"""
from datetime import datetime, time as dtime, timedelta

from django.utils import timezone

from appointments.models import Appointment

# Рабочее окно салона и шаг сетки слотов (минуты) — единственное место определения.
DAY_START, DAY_END, STEP = 8, 23, 15


def _busy_intervals(employee, day):
    """Занятые интервалы мастера в этот день (все записи, кроме «не пришёл»)."""
    busy = []
    qs = (Appointment.objects
          .filter(employee=employee, start__date=day)
          .exclude(status=Appointment.STATUS_NOSHOW))
    for a in qs:
        s = timezone.localtime(a.start)
        busy.append((s, s + timedelta(minutes=a.duration_min)))
    return busy


def free_slots(employee, day, duration_min):
    """Свободные начала слотов для мастера в этот день (с учётом смены и занятости).

    Возвращает список aware-datetime (локальная TZ). Пустой список — мастер не в
    смене в этот день или свободных окон нет.
    """
    if not employee.on_shift(day):
        return []

    day_start = timezone.make_aware(datetime.combine(day, dtime(DAY_START, 0)))
    day_end = timezone.make_aware(datetime.combine(day, dtime(DAY_END, 0)))
    dur = timedelta(minutes=duration_min or 60)
    now = timezone.localtime()
    today = timezone.localdate()
    busy = _busy_intervals(employee, day)

    slots = []
    t = day_start
    while t + dur <= day_end:
        past = (day == today and t <= now)
        if not past and not any(t < be and (t + dur) > bs for bs, be in busy):
            slots.append(t)
        t += timedelta(minutes=STEP)
    return slots


def is_slot_free(employee, start, duration_min):
    """Свободно ли конкретное начало `start` у мастера (строго одно из валидных окон).

    Используется при создании записи как финальная проверка против гонки
    «показали слот → его заняли, пока клиент оформлял».
    """
    return any(t == start for t in free_slots(employee, start.date(), duration_min))


def available_days(employees, duration_min, days=14):
    """Даты в ближайшие `days` дней, где хотя бы у одного мастера есть свободный слот.

    Нужно для экрана выбора даты и для фида «доступных дат» внешним площадкам.
    """
    result = []
    base = timezone.localdate()
    for i in range(days):
        day = base + timedelta(days=i)
        if any(free_slots(e, day, duration_min) for e in employees):
            result.append(day)
    return result
