"""
Сотрудники: ростер (сайдбар) и управление (в Настройках).

Ростер — только просмотр: вкладки Работают/Уволенные, внутри работающих деление
на «в смене сегодня» и «не в смене». Создание/редактирование вынесено в Настройки.
"""
from collections import Counter
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from appointments.models import Appointment
from core.permissions import has_perm, requires, requires_any
from staff.models import Employee

WEEKDAYS = [(0, "Пн"), (1, "Вт"), (2, "Ср"), (3, "Чт"), (4, "Пт"), (5, "Сб"), (6, "Вс")]

# Пока нет модуля расчёта ЗП — ставка-заглушка для ОЦЕНКИ (явно помечаем в UI).
DEFAULT_COMMISSION = 0.40
STAT_PERIODS = [("today", "Сегодня"), ("week", "7 дней"), ("month", "Этот месяц")]


def _period_range(period, today):
    if period == "today":
        return today, today
    if period == "week":
        return today - timedelta(days=6), today
    return today.replace(day=1), today  # month-to-date


def _today_counts(day):
    """Сколько записей сегодня у каждого мастера (не считая неявки)."""
    rows = (
        Appointment.objects.filter(start__date=day)
        .exclude(status=Appointment.STATUS_NOSHOW)
        .values("employee_id")
        .annotate(n=Count("id"))
    )
    return {r["employee_id"]: r["n"] for r in rows}


# --- Ростер сотрудников (пункт сайдбара, только просмотр) ---
@login_required
@requires("staff.view")
def staff_list(request):
    tab = request.GET.get("tab", "working")
    today = timezone.localdate()
    counts = _today_counts(today)

    def pack(e):
        return {
            "e": e,
            "count": counts.get(e.id, 0),
            "on_shift": e.on_shift(today),
            "days": [lbl for d, lbl in WEEKDAYS if d in (e.work_days or [])],
        }

    if tab == "dismissed":
        dismissed = [pack(e) for e in Employee.objects.filter(is_active=False)]
        context = {"tab": tab, "dismissed": dismissed}
    else:
        tab = "working"
        working = Employee.objects.filter(is_active=True)
        on_shift = [pack(e) for e in working if e.on_shift(today)]
        off_shift = [pack(e) for e in working if not e.on_shift(today)]
        context = {"tab": tab, "on_shift": on_shift, "off_shift": off_shift}

    context["today"] = today
    context["can_manage"] = has_perm(request.user, "staff.create") or has_perm(request.user, "staff.edit")
    return render(request, "staff/list.html", context)


# --- Карточка сотрудника: личные показатели (клик по строке в ростере) ---
@login_required
@requires("staff.view")
def staff_detail(request, pk):
    e = get_object_or_404(Employee, pk=pk)
    today = timezone.localdate()
    period = request.GET.get("period", "month")
    if period not in dict(STAT_PERIODS):
        period = "month"
    start, end = _period_range(period, today)

    came = (
        Appointment.objects.filter(employee=e, status=Appointment.STATUS_CAME,
                                    start__date__gte=start, start__date__lte=end)
        .prefetch_related("lines__service")
    )

    revenue = 0
    visits = 0
    duration_min = 0
    extra_count = 0        # доп. услуги сверх первой
    extra_sum = 0          # деньги с доп. услуг
    clients = set()
    services = Counter()
    for a in came:
        visits += 1
        revenue += a.price
        duration_min += a.duration_min
        clients.add(a.client_id)
        lines = list(a.lines.all())
        for i, ln in enumerate(lines):
            services[ln.service.name if ln.service else "—"] += 1
            if i > 0:
                extra_count += 1
                extra_sum += ln.price

    revenue = int(revenue)
    extra_sum = int(extra_sum)
    avg_check = int(revenue / visits) if visits else 0

    noshow = Appointment.objects.filter(
        employee=e, status=Appointment.STATUS_NOSHOW,
        start__date__gte=start, start__date__lte=end
    ).count()

    # Отработанные часы (по проведённым визитам) и смены по графику
    hours = round(duration_min / 60, 1)
    scheduled_days = 0
    d = start
    while d <= end:
        if e.on_shift(d):
            scheduled_days += 1
        d += timedelta(days=1)

    salary_est = int(revenue * DEFAULT_COMMISSION)

    context = {
        "e": e,
        "periods": STAT_PERIODS, "period": period, "start": start, "end": end,
        "work_days": [lbl for code, lbl in WEEKDAYS if code in (e.work_days or [])],
        "revenue": revenue, "visits": visits, "clients": len(clients),
        "avg_check": avg_check, "hours": hours, "scheduled_days": scheduled_days,
        "extra_count": extra_count, "extra_sum": extra_sum, "noshow": noshow,
        "salary_est": salary_est, "commission_pct": int(DEFAULT_COMMISSION * 100),
        "top_services": services.most_common(6),
        "can_manage": has_perm(request.user, "staff.edit"),
    }
    return render(request, "staff/detail.html", context)


# --- Управление сотрудниками (в Настройках): список + создание ---
@login_required
@requires_any("staff.create", "staff.edit", "staff.schedule.edit")
def staff_manage(request):
    employees = Employee.objects.all()
    rows = [{"e": e, "work_days": e.work_days or []} for e in employees]
    return render(request, "staff/manage.html", {"rows": rows, "weekdays": WEEKDAYS})


def _read_work_days(request):
    out = []
    for v in request.POST.getlist("work_days"):
        try:
            d = int(v)
        except ValueError:
            continue
        if 0 <= d <= 6:
            out.append(d)
    return sorted(set(out))


# --- Создание сотрудника ---
@login_required
@requires("staff.create")
@require_POST
def staff_create(request):
    name = (request.POST.get("full_name") or "").strip()
    if name:
        Employee.objects.create(
            full_name=name,
            specialization=(request.POST.get("specialization") or "").strip(),
            phone=(request.POST.get("phone") or "").strip(),
            color=(request.POST.get("color") or "#0071E3").strip(),
            work_days=_read_work_days(request),
        )
    return redirect("staff_manage")


# --- Редактирование сотрудника ---
@login_required
@requires("staff.edit")
@require_POST
def staff_edit(request, pk):
    e = get_object_or_404(Employee, pk=pk)
    e.full_name = (request.POST.get("full_name") or e.full_name).strip()
    e.specialization = (request.POST.get("specialization") or "").strip()
    e.phone = (request.POST.get("phone") or "").strip()
    e.color = (request.POST.get("color") or "#0071E3").strip()
    e.work_days = _read_work_days(request)
    e.save(update_fields=["full_name", "specialization", "phone", "color", "work_days"])
    return redirect("staff_manage")


# --- Увольнение / восстановление ---
@login_required
@requires("staff.edit")
@require_POST
def staff_toggle(request, pk):
    e = get_object_or_404(Employee, pk=pk)
    e.is_active = not e.is_active
    e.save(update_fields=["is_active"])
    return redirect("staff_manage")
