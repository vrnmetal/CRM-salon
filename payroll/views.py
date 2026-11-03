"""Зарплаты: расчёт по сотрудникам + управление схемами и их назначением."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.permissions import requires
from payroll.engine import compute
from payroll.models import PayrollScheme, PayrollTier
from staff.models import Employee

PERIODS = [("today", "Сегодня"), ("week", "7 дней"), ("month", "Этот месяц")]


def _range(period, today):
    if period == "today":
        return today, today
    if period == "week":
        return today - timedelta(days=6), today
    return today.replace(day=1), today


def _dec(raw, default="0"):
    try:
        return Decimal(str(raw).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


# --- Расчёт ЗП по сотрудникам ---
@login_required
@requires("payroll.view")
def payroll_home(request):
    today = timezone.localdate()
    period = request.GET.get("period", "month")
    if period not in dict(PERIODS):
        period = "month"
    start, end = _range(period, today)

    rows = [compute(e, start, end) for e in Employee.objects.filter(is_active=True)]
    total = sum(r["total"] for r in rows)
    return render(request, "payroll/home.html", {
        "rows": rows, "total": total, "periods": PERIODS, "period": period,
        "start": start, "end": end,
    })


# --- Вкладка «Схемы»: список схем + сотрудники с их схемами ---
@login_required
@requires("payroll.manage")
def schemes_list(request):
    schemes = PayrollScheme.objects.annotate(ntiers=Count("tiers")).all()
    employees = Employee.objects.filter(is_active=True).select_related("payroll_scheme")
    return render(request, "payroll/schemes_list.html", {
        "schemes": schemes, "employees": employees,
    })


# --- Создание схемы → сразу в её редактор ---
@login_required
@requires("payroll.manage")
def scheme_new(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if name:
            s = PayrollScheme.objects.create(name=name, base_per_day=_dec(request.POST.get("base_per_day")))
            PayrollTier.objects.create(scheme=s, min_revenue=0, pct=_dec(request.POST.get("base_pct")))
            messages.success(request, f"Схема «{name}» создана.")
            return redirect("payroll_scheme_edit", pk=s.id)
        messages.error(request, "Укажите название схемы.")
    return render(request, "payroll/scheme_new.html")


# --- Редактор одной схемы ---
@login_required
@requires("payroll.manage")
def scheme_edit(request, pk):
    scheme = get_object_or_404(PayrollScheme, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save":
            scheme.name = (request.POST.get("name") or scheme.name).strip()
            scheme.base_per_day = _dec(request.POST.get("base_per_day"))
            scheme.save(update_fields=["name", "base_per_day"])
            messages.success(request, "Схема сохранена.")
        elif action == "tier_add":
            PayrollTier.objects.update_or_create(
                scheme=scheme, min_revenue=_dec(request.POST.get("min_revenue")),
                defaults={"pct": _dec(request.POST.get("pct"))})
            messages.success(request, "Порог добавлен.")
        elif action == "tier_remove":
            PayrollTier.objects.filter(scheme=scheme, pk=request.POST.get("tier")).delete()
        elif action == "delete":
            scheme.delete()
            messages.info(request, "Схема удалена.")
            return redirect("payroll_schemes")
        return redirect("payroll_scheme_edit", pk=scheme.id)

    return render(request, "payroll/scheme_edit.html", {"scheme": scheme})


# --- Назначение схемы сотруднику (отдельная вьюха) ---
@login_required
@requires("payroll.manage")
def assign_scheme(request, employee_pk):
    e = get_object_or_404(Employee, pk=employee_pk)
    if request.method == "POST":
        e.payroll_scheme = PayrollScheme.objects.filter(pk=request.POST.get("scheme")).first()
        e.save(update_fields=["payroll_scheme"])
        messages.success(request, f"Схема сотрудника {e.full_name} обновлена.")
        return redirect("payroll_schemes")
    schemes = PayrollScheme.objects.filter(is_active=True)
    return render(request, "payroll/assign.html", {"e": e, "schemes": schemes})
