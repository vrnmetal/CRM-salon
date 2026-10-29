"""
Финансы и касса (первый слой — без фискализации).

Пока это честная касса/аналитика по ПРОВЕДЁННЫМ визитам (статус «пришёл»):
выручка за период, разбивка по мастерам, услугам и дням, упущенное на неявках.
Эквайринг, чеки (54-ФЗ) и драйвер к провайдеру навесим отдельным слоем позже.
"""
from datetime import date as date_cls, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone

from appointments.models import Appointment, AppointmentService
from core.permissions import requires

PERIODS = [("today", "Сегодня"), ("week", "7 дней"), ("month", "Этот месяц")]
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _range(period, today):
    if period == "today":
        return today, today
    if period == "week":
        return today - timedelta(days=6), today
    return today.replace(day=1), today  # month-to-date


@login_required
@requires("finance.view")
def finance_home(request):
    today = timezone.localdate()
    period = request.GET.get("period", "month")

    # Произвольный диапазon: ?from=YYYY-MM-DD&to=YYYY-MM-DD
    def _d(raw):
        try:
            return date_cls.fromisoformat(raw)
        except (TypeError, ValueError):
            return None

    custom_from, custom_to = _d(request.GET.get("from")), _d(request.GET.get("to"))
    if custom_from and custom_to:
        period = "custom"
        start, end = min(custom_from, custom_to), max(custom_from, custom_to)
        # Ограничим размах, чтобы по-дневный цикл не разросся
        if (end - start).days > 366:
            start = end - timedelta(days=366)
    else:
        if period not in dict(PERIODS):
            period = "month"
        start, end = _range(period, today)

    came = Appointment.objects.filter(
        status=Appointment.STATUS_CAME, start__date__gte=start, start__date__lte=end
    )
    visits = came.count()
    revenue = int(came.aggregate(s=Sum("price"))["s"] or 0)
    avg_check = int(revenue / visits) if visits else 0

    # Упущено на неявках за период
    noshow = Appointment.objects.filter(
        status=Appointment.STATUS_NOSHOW, start__date__gte=start, start__date__lte=end
    )
    missed = int(noshow.aggregate(s=Sum("price"))["s"] or 0)
    missed_count = noshow.count()

    # По мастерам
    by_master = [
        {"name": r["employee__full_name"], "sum": int(r["s"] or 0), "visits": r["n"]}
        for r in came.values("employee__full_name").annotate(s=Sum("price"), n=Count("id")).order_by("-s")
    ]

    # По услугам (строки услуг проведённых визитов — точнее, чем одна услуга записи)
    lines = AppointmentService.objects.filter(
        appointment__status=Appointment.STATUS_CAME,
        appointment__start__date__gte=start, appointment__start__date__lte=end,
    )
    by_service = [
        {"name": r["service__name"] or "—", "sum": int(r["s"] or 0), "count": r["n"]}
        for r in lines.values("service__name").annotate(s=Sum("price"), n=Count("id")).order_by("-s")
    ]

    # По дням
    days = []
    d = start
    while d <= end:
        rev = int(came.filter(start__date=d).aggregate(s=Sum("price"))["s"] or 0)
        days.append({"date": d, "label": f"{d.day:02d}.{d.month:02d}", "dow": WEEKDAYS[d.weekday()],
                     "rev": rev, "is_today": d == today})
        d += timedelta(days=1)
    max_rev = max((x["rev"] for x in days), default=0) or 1
    for x in days:
        x["pct"] = round(100 * x["rev"] / max_rev)

    context = {
        "periods": PERIODS, "period": period, "start": start, "end": end,
        "today_iso": today.isoformat(), "start_iso": start.isoformat(), "end_iso": end.isoformat(),
        "revenue": revenue, "visits": visits, "avg_check": avg_check,
        "missed": missed, "missed_count": missed_count,
        "by_master": by_master, "by_service": by_service, "days": days,
    }
    return render(request, "finance/finance.html", context)
