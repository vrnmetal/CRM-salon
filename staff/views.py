"""
Сотрудники: ростер (сайдбар) и управление (в Настройках).

Ростер — только просмотр: вкладки Работают/Уволенные, внутри работающих деление
на «в смене сегодня» и «не в смене». Создание/редактирование вынесено в Настройки.
"""
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
