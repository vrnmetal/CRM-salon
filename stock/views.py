"""Склад: материалы, движения (приход/списание/корректировка), тех. карты услуг."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from django.urls import reverse

from appointments.models import Service
from core.permissions import requires
from stock.models import AppointmentMaterial, Material, StockMovement, TechCardItem


def _dec(raw, default="0"):
    try:
        return Decimal(str(raw).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


# --- Склад: материалы + последние движения ---
@login_required
@requires("stock.view")
def stock_home(request):
    materials = list(Material.objects.all())
    low = [m for m in materials if m.is_low]
    mat_rows = [{"m": m, "value": int((m.quantity or 0) * (m.cost_per_unit or 0))} for m in materials]
    total_value = sum(r["value"] for r in mat_rows)
    movements = StockMovement.objects.select_related("material")[:15]
    return render(request, "stock/home.html", {
        "mat_rows": mat_rows, "has_materials": bool(materials),
        "low_count": len(low), "movements": movements, "total_value": total_value,
    })


# --- Создать материал ---
@login_required
@requires("stock.manage")
@require_POST
def material_create(request):
    name = (request.POST.get("name") or "").strip()
    if name:
        qty = _dec(request.POST.get("quantity"))
        m = Material.objects.create(
            name=name,
            unit=(request.POST.get("unit") or "шт"),
            quantity=qty,
            low_threshold=_dec(request.POST.get("low_threshold")),
            cost_per_unit=_dec(request.POST.get("cost_per_unit")),
            waste_pct=_dec(request.POST.get("waste_pct")),
        )
        if qty > 0:
            StockMovement.objects.create(material=m, delta=qty,
                                         reason=StockMovement.PURCHASE, note="Начальный остаток")
        messages.success(request, f"Материал «{name}» добавлен.")
    return redirect("stock_home")


# --- Изменить данные материала ---
@login_required
@requires("stock.manage")
@require_POST
def material_edit(request, pk):
    m = get_object_or_404(Material, pk=pk)
    m.name = (request.POST.get("name") or m.name).strip()
    m.unit = request.POST.get("unit") or m.unit
    m.low_threshold = _dec(request.POST.get("low_threshold"))
    m.cost_per_unit = _dec(request.POST.get("cost_per_unit"))
    m.waste_pct = _dec(request.POST.get("waste_pct"))
    m.save(update_fields=["name", "unit", "low_threshold", "cost_per_unit", "waste_pct"])
    messages.success(request, "Материал обновлён.")
    return redirect("stock_home")


# --- Движение: приход / списание / корректировка ---
@login_required
@requires("stock.manage")
@require_POST
def material_move(request, pk):
    m = get_object_or_404(Material, pk=pk)
    qty = _dec(request.POST.get("qty"))
    direction = request.POST.get("direction")  # in / out
    if qty <= 0:
        messages.error(request, "Количество должно быть больше нуля.")
        return redirect("stock_home")

    note = (request.POST.get("note") or "").strip()

    if direction == "in":
        delta = qty
        # Средневзвешенная себестоимость: если указана цена закупки — пересчитываем
        raw_price = request.POST.get("purchase_price")
        price = _dec(raw_price) if raw_price not in (None, "") else None
        old_q = m.quantity or 0
        if price is not None and price > 0 and (old_q + qty) > 0:
            m.cost_per_unit = (old_q * (m.cost_per_unit or 0) + qty * price) / (old_q + qty)
            m.quantity = old_q + qty
            m.save(update_fields=["quantity", "cost_per_unit"])
            note = (note + f" · закупка {price:.0f} ₽/{m.unit} → средняя {m.cost_per_unit:.2f}").strip(" ·")
        else:
            m.quantity = old_q + qty
            m.save(update_fields=["quantity"])
        reason = StockMovement.PURCHASE
    else:
        delta = -qty
        m.quantity = (m.quantity or 0) - qty
        m.save(update_fields=["quantity"])
        reason = StockMovement.ADJUST

    StockMovement.objects.create(material=m, delta=delta, reason=reason, note=note)
    messages.success(request, f"{'Приход' if delta > 0 else 'Списание'} {abs(delta)} {m.unit} · {m.name}.")
    return redirect("stock_home")


# --- Сколько процедур услуги обеспечено текущим запасом (минимум по материалам) ---
def _possible_from_items(items):
    caps = []
    for it in items:
        eff = it.effective_qty  # расход с учётом потерь
        if eff and eff > 0:
            caps.append(int(it.material.quantity // eff))
    return min(caps) if caps else None


# --- Тех. карты: список услуг с себестоимостью, маржой и остатком в процедурах ---
@login_required
@requires("stock.view")
def techcards(request):
    services = list(Service.objects.all())
    items_by = {}
    cost_by = {}
    for it in TechCardItem.objects.select_related("material"):
        items_by.setdefault(it.service_id, []).append(it)
        cost_by[it.service_id] = cost_by.get(it.service_id, Decimal("0")) + it.line_cost
    rows = []
    for s in services:
        items = items_by.get(s.id, [])
        cost = cost_by.get(s.id, Decimal("0"))
        rows.append({
            "s": s, "cost": int(cost), "items": len(items),
            "margin": int((s.price or 0) - cost),
            "possible": _possible_from_items(items),
        })
    return render(request, "stock/techcards.html", {"rows": rows})


# --- Редактор тех. карты услуги ---
@login_required
@requires("techcard.edit")
def service_card(request, service_pk):
    service = get_object_or_404(Service, pk=service_pk)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add":
            material = Material.objects.filter(pk=request.POST.get("material")).first()
            qty = _dec(request.POST.get("qty"))
            if material and qty > 0:
                TechCardItem.objects.update_or_create(
                    service=service, material=material, defaults={"qty": qty})
                messages.success(request, "Строка тех. карты сохранена.")
        elif action == "remove":
            TechCardItem.objects.filter(service=service, pk=request.POST.get("item")).delete()
            messages.info(request, "Строка удалена.")
        return redirect("service_card", service_pk=service.id)

    items = list(TechCardItem.objects.filter(service=service).select_related("material"))
    cost = sum((it.line_cost for it in items), Decimal("0"))
    # На сколько процедур хватает каждого материала и услуги в целом
    rows = []
    for it in items:
        eff = it.effective_qty
        cap = int(it.material.quantity // eff) if eff and eff > 0 else None
        rows.append({"it": it, "cap": cap})
    possible = _possible_from_items(items)
    materials = Material.objects.filter(is_active=True)
    return render(request, "stock/card.html", {
        "service": service, "rows": rows, "cost": int(cost), "possible": possible,
        "margin": int((service.price or 0) - cost), "materials": materials,
    })


# ============================================================================
# Расход материалов по КОНКРЕТНОЙ записи (разовая корректировка тех. карты)
# ============================================================================
def _back_to_appt(appt_id):
    from django.shortcuts import redirect
    return redirect(reverse("appointment_detail", args=[appt_id]))


# --- Заполнить расход из тех. карт услуг записи (потом можно править) ---
@login_required
@requires("stock.manage")
@require_POST
def appt_fill(request, appt_pk):
    from appointments.models import Appointment, AppointmentService
    appt = get_object_or_404(Appointment, pk=appt_pk)
    agg = {}
    for line in AppointmentService.objects.filter(appointment=appt):
        for it in TechCardItem.objects.filter(service_id=line.service_id).select_related("material"):
            agg[it.material] = agg.get(it.material, 0) + it.effective_qty
    for mat, q in agg.items():
        AppointmentMaterial.objects.update_or_create(appointment=appt, material=mat, defaults={"qty": q})
    messages.success(request, "Расход заполнен из тех. карт — поправьте по факту при необходимости.")
    return _back_to_appt(appt_pk)


# --- Добавить/изменить материал в расходе записи ---
@login_required
@requires("stock.manage")
@require_POST
def appt_mat_set(request, appt_pk):
    from appointments.models import Appointment
    appt = get_object_or_404(Appointment, pk=appt_pk)
    mat = Material.objects.filter(pk=request.POST.get("material")).first()
    q = _dec(request.POST.get("qty"))
    if mat and q > 0:
        AppointmentMaterial.objects.update_or_create(appointment=appt, material=mat, defaults={"qty": q})
        messages.success(request, "Расход по записи сохранён.")
    return _back_to_appt(appt_pk)


# --- Убрать материал из расхода записи ---
@login_required
@requires("stock.manage")
@require_POST
def appt_mat_remove(request, pk):
    row = get_object_or_404(AppointmentMaterial, pk=pk)
    appt_id = row.appointment_id
    row.delete()
    return _back_to_appt(appt_id)
