"""Движок расчёта ЗП: оклад за отработанные смены + прогрессивный % с выручки."""
from decimal import Decimal

from django.db.models import Count, Sum

from appointments.models import Appointment


def applied_rate(scheme, revenue):
    """Ставка самого высокого порога, не превышающего выручку (прогрессия)."""
    rate = Decimal("0")
    if scheme is None:
        return rate
    for tier in scheme.tiers.all().order_by("min_revenue"):
        if revenue >= tier.min_revenue:
            rate = tier.pct
    return rate


def compute(employee, start, end):
    """Расчёт ЗП сотрудника за период [start, end]."""
    scheme = employee.payroll_scheme
    came = Appointment.objects.filter(
        employee=employee, status=Appointment.STATUS_CAME,
        start__date__gte=start, start__date__lte=end,
    )
    agg = came.aggregate(rev=Sum("price"))
    revenue = agg["rev"] or Decimal("0")
    visits = came.count()
    # Отработанные смены = дни, когда были проведённые визиты
    days = came.values("start__date").distinct().count()

    base_per_day = scheme.base_per_day if scheme else Decimal("0")
    base = base_per_day * days
    rate = applied_rate(scheme, revenue)
    commission = revenue * rate / Decimal("100")
    total = base + commission

    return {
        "employee": employee,
        "scheme": scheme,
        "revenue": int(revenue),
        "visits": visits,
        "days": days,
        "base": int(base),
        "rate": rate,
        "commission": int(commission),
        "total": int(total),
    }
