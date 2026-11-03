"""
Публичный портал онлайн-записи (без входа).

Тенант резолвится по slug из URL (/book/<slug>/), чтобы работало и на поддомене,
и на 127.0.0.1 при разработке. Все запросы к данным оборачиваем в tenant_context,
чтобы изоляция по тенанту работала как обычно. White-label: бренд салона.
"""
from datetime import datetime, timedelta

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from appointments.models import Appointment, Service, ServiceCategory
from appointments.slots import free_slots as _free_slots, is_slot_free
from clients.models import Client
from core.models import Tenant
from core.tenancy import tenant_context
from staff.models import Employee


def _get_tenant(slug):
    t = Tenant.objects.filter(slug=slug, is_active=True).first()
    if t is None:
        raise Http404("Салон не найден")
    return t


def _brand(tenant):
    return {
        "name": tenant.brand_name or tenant.name,
        "accent": tenant.accent_color or "",
        "logo_url": tenant.logo.url if tenant.logo else "",
        "font": tenant.font_preset or "",
    }


def _booking_on(tenant):
    return "booking" in (tenant.enabled_modules or [])


# Слоты считаются единым сервисом appointments.slots (см. импорт выше) —
# один источник правды для журнала, портала и внешних интеграций.


# --- Шаг 1: выбор услуги ---
def book_services(request, slug):
    tenant = _get_tenant(slug)
    with tenant_context(tenant):
        if not _booking_on(tenant):
            return render(request, "booking/unavailable.html", {"brand": _brand(tenant)})
        cats = list(ServiceCategory.objects.all())
        services = list(Service.objects.filter(is_active=True).select_related("category"))
        by_cat = {}
        for s in services:
            by_cat.setdefault(s.category_id, []).append(s)
        groups = [{"cat": c, "items": by_cat.get(c.id, [])} for c in cats if by_cat.get(c.id)]
        # услуги без категории
        no_cat = by_cat.get(None, [])
        if no_cat:
            groups.append({"cat": None, "items": no_cat})
    return render(request, "booking/services.html", {
        "brand": _brand(tenant), "slug": slug, "groups": groups,
    })


# --- Шаг 2: выбор мастера, даты и слота ---
def book_slots(request, slug, service_id):
    tenant = _get_tenant(slug)
    with tenant_context(tenant):
        if not _booking_on(tenant):
            return render(request, "booking/unavailable.html", {"brand": _brand(tenant)})
        service = get_object_or_404(Service, pk=service_id, is_active=True)
        masters = list(Employee.objects.filter(is_active=True))

        # Дата
        raw = request.GET.get("date")
        try:
            day = datetime.fromisoformat(raw).date() if raw else timezone.localdate()
        except ValueError:
            day = timezone.localdate()

        emp_id = request.GET.get("emp") or "any"

        # Слоты
        if emp_id == "any":
            # объединяем слоты всех мастеров, помним первого свободного на каждое время
            slot_map = {}
            for m in masters:
                for t in _free_slots(m, day, service.duration_min):
                    slot_map.setdefault(t, m)
            slots = [{"time": t, "emp": slot_map[t]} for t in sorted(slot_map)]
        else:
            m = next((x for x in masters if str(x.id) == str(emp_id)), None)
            slots = [{"time": t, "emp": m} for t in _free_slots(m, day, service.duration_min)] if m else []

        days = [timezone.localdate() + timedelta(days=i) for i in range(14)]

    return render(request, "booking/slots.html", {
        "brand": _brand(tenant), "slug": slug, "service": service,
        "masters": masters, "emp_id": emp_id, "day": day, "days": days, "slots": slots,
    })


# --- Шаг 3: подтверждение (имя/телефон/согласие) и создание записи ---
@require_POST
def book_confirm(request, slug):
    tenant = _get_tenant(slug)
    with tenant_context(tenant):
        if not _booking_on(tenant):
            return render(request, "booking/unavailable.html", {"brand": _brand(tenant)})

        service = get_object_or_404(Service, pk=request.POST.get("service"), is_active=True)
        emp = get_object_or_404(Employee, pk=request.POST.get("emp"), is_active=True)
        name = (request.POST.get("name") or "").strip()
        phone = (request.POST.get("phone") or "").strip()
        consent = bool(request.POST.get("consent"))

        try:
            start_naive = datetime.fromisoformat(request.POST.get("start"))
        except (ValueError, TypeError):
            messages.error(request, "Некорректное время.")
            return redirect("book_slots", slug=slug, service_id=service.id)

        if not (name and phone and consent):
            return render(request, "booking/confirm.html", {
                "brand": _brand(tenant), "slug": slug, "service": service, "emp": emp,
                "start": request.POST.get("start"), "error": "Заполните имя, телефон и согласие.",
                "name": name, "phone": phone,
            })

        start = timezone.make_aware(start_naive) if timezone.is_naive(start_naive) else start_naive

        # Проверяем, что слот ещё свободен
        if not is_slot_free(emp, start, service.duration_min):
            messages.error(request, "Это время только что заняли. Выберите другое.")
            return redirect("book_slots", slug=slug, service_id=service.id)

        client, _ = Client.objects.get_or_create(phone=phone, defaults={"full_name": name})
        if name and not client.full_name:
            client.full_name = name
            client.save(update_fields=["full_name"])

        appt = Appointment.objects.create(
            client=client, employee=emp, service=service, start=start,
            duration_min=service.duration_min, price=service.price,
            status=Appointment.STATUS_WAIT, pdn_consent=consent,
            comment="Онлайн-запись", source=Appointment.SOURCE_PORTAL,
        )
        from appointments.models import AppointmentService
        AppointmentService.objects.create(appointment=appt, service=service, price=service.price)

    return redirect("book_done", slug=slug, appt_id=appt.id)


# --- Экран подтверждения формы (GET из слота) ---
def book_form(request, slug, service_id):
    tenant = _get_tenant(slug)
    with tenant_context(tenant):
        if not _booking_on(tenant):
            return render(request, "booking/unavailable.html", {"brand": _brand(tenant)})
        service = get_object_or_404(Service, pk=service_id, is_active=True)
        emp = get_object_or_404(Employee, pk=request.GET.get("emp"), is_active=True)
        start = request.GET.get("start")
    return render(request, "booking/confirm.html", {
        "brand": _brand(tenant), "slug": slug, "service": service, "emp": emp, "start": start,
    })


# --- Готово ---
def book_done(request, slug, appt_id):
    tenant = _get_tenant(slug)
    with tenant_context(tenant):
        appt = get_object_or_404(
            Appointment.objects.select_related("service", "employee"), pk=appt_id)
    return render(request, "booking/done.html", {"brand": _brand(tenant), "a": appt})
