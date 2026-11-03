"""
Эндпоинты Maps Booking Partner API (сервер на нашей стороне, Яндекс — клиент).

Все пути смонтированы под /yandex/v1/ (см. urls.py). Данные каждого салона берём
в его tenant_context; слоты считает единый сервис appointments.slots.
"""
from decimal import Decimal

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from appointments.models import Appointment, AppointmentService, Service
from appointments.slots import free_slots, is_slot_free
from clients.models import Client
from core.models import Tenant
from core.tenancy import tenant_context
from staff.models import Employee
from yandex_booking import mappers
from yandex_booking.auth import json_error, parse_body, read_payload, require_claim
from yandex_booking.signals import suppress

MODULE = "yandex_booking"


# ---------------------------------------------------------------------------
# Вспомогательное
# ---------------------------------------------------------------------------
def _base_url(request):
    return request.build_absolute_uri("/").rstrip("/")


def _resolve_company(company_id):
    """Тенант по companyId (=slug), активный и с включённым модулем. Иначе None."""
    t = Tenant.objects.filter(slug=company_id, is_active=True).first()
    if t is None or not t.is_module_on(MODULE):
        return None
    return t


def _active_employees():
    return list(Employee.objects.filter(is_active=True))


def _duration_for(service_ids):
    secs = 0
    for s in Service.objects.filter(id__in=service_ids):
        secs += (s.duration_min or 60)
    return secs or 60


def _qlist(request, key):
    # serviceIds[]=a&serviceIds[]=b  или  serviceIds=a,b
    vals = request.GET.getlist(key) or request.GET.getlist(key + "[]")
    if len(vals) == 1 and "," in vals[0]:
        vals = [v for v in vals[0].split(",") if v]
    return vals


# ---------------------------------------------------------------------------
# Фид организаций
# ---------------------------------------------------------------------------
def companies_feed(request):
    payload, err = read_payload(request)
    if err:
        return err
    try:
        count = max(1, min(500, int(request.GET.get("count", 100))))
    except (ValueError, TypeError):
        count = 100
    cursor = request.GET.get("cursor") or ""

    # Кросс-тенантно: все активные салоны с включённым модулем, по slug.
    tenants = [t for t in Tenant.objects.filter(is_active=True).order_by("slug")
               if t.is_module_on(MODULE)]
    if cursor:
        tenants = [t for t in tenants if t.slug > cursor]
    page = tenants[:count]
    has_more = len(tenants) > count
    base = _base_url(request)
    companies = [mappers.company_json(t, base) for t in page]
    next_cursor = page[-1].slug if page and has_more else ""
    return JsonResponse({
        "companies": companies,
        "pagination": {"cursor": next_cursor, "hasMore": has_more},
    })


# ---------------------------------------------------------------------------
# Услуги / ресурсы / отзывы
# ---------------------------------------------------------------------------
def company_services(request, company_id):
    payload, err = read_payload(request)
    if err:
        return err
    if (e := require_claim(payload, "companyId", company_id)):
        return e
    tenant = _resolve_company(company_id)
    if tenant is None:
        return json_error(404, "COMPANY_NOT_FOUND")
    with tenant_context(tenant):
        employees = _active_employees()
        services = list(Service.objects.filter(is_active=True).select_related("category"))
        data = [mappers.service_json(s, employees) for s in services]
    return JsonResponse({"services": data})


def company_resources(request, company_id):
    payload, err = read_payload(request)
    if err:
        return err
    if (e := require_claim(payload, "companyId", company_id)):
        return e
    tenant = _resolve_company(company_id)
    if tenant is None:
        return json_error(404, "COMPANY_NOT_FOUND")
    with tenant_context(tenant):
        data = [mappers.resource_json(emp) for emp in _active_employees()]
    return JsonResponse({"resources": data})


def resource_reviews(request, company_id, resource_id):
    payload, err = read_payload(request)
    if err:
        return err
    if (e := require_claim(payload, "companyId", company_id)):
        return e
    # Отзывы не ведём (reviewsCount=0, этот метод Яндекс обычно не вызывает).
    return JsonResponse({"reviews": []})


def special_conditions(request, company_id):
    payload, err = read_payload(request)
    if err:
        return err
    if (e := require_claim(payload, "companyId", company_id)):
        return e
    return JsonResponse({"specialConditions": []})


# ---------------------------------------------------------------------------
# Доступные даты и слоты
# ---------------------------------------------------------------------------
def _employees_for(resource_id):
    if resource_id:
        emp = Employee.objects.filter(pk=resource_id, is_active=True).first()
        return [emp] if emp else []
    return _active_employees()


def available_dates(request, company_id):
    from datetime import date as _date, timedelta

    payload, err = read_payload(request)
    if err:
        return err
    if (e := require_claim(payload, "companyId", company_id)):
        return e
    tenant = _resolve_company(company_id)
    if tenant is None:
        return json_error(404, "COMPANY_NOT_FOUND")

    service_ids = _qlist(request, "serviceIds")
    resource_id = request.GET.get("resourceId")
    try:
        d_from = _date.fromisoformat(request.GET["from"])
        d_to = _date.fromisoformat(request.GET["to"])
    except (KeyError, ValueError):
        return json_error(422, "BAD_RANGE", "Нужны from и to в формате YYYY-MM-DD")

    out = []
    with tenant_context(tenant):
        dur = _duration_for(service_ids)
        employees = _employees_for(resource_id)
        day = d_from
        while day <= d_to:
            if any(free_slots(e, day, dur) for e in employees):
                out.append({"date": f"{day.isoformat()}T00:00:00.000Z"})
            day += timedelta(days=1)
    return JsonResponse({"availableDates": out})


def available_time_slots(request, company_id):
    from datetime import date as _date

    payload, err = read_payload(request)
    if err:
        return err
    if (e := require_claim(payload, "companyId", company_id)):
        return e
    tenant = _resolve_company(company_id)
    if tenant is None:
        return json_error(404, "COMPANY_NOT_FOUND")

    service_ids = _qlist(request, "serviceIds")
    resource_id = request.GET.get("resourceId")
    try:
        day = _date.fromisoformat(request.GET["date"])
    except (KeyError, ValueError):
        return json_error(422, "BAD_DATE", "Нужна date в формате YYYY-MM-DD")

    moments = set()
    with tenant_context(tenant):
        dur = _duration_for(service_ids)
        for e in _employees_for(resource_id):
            for t in free_slots(e, day, dur):
                moments.add(t)
    slots = [{"datetime": mappers.to_utc_iso(t)} for t in sorted(moments)]
    return JsonResponse({"availableTimeSlots": slots})


# ---------------------------------------------------------------------------
# Записи
# ---------------------------------------------------------------------------
@csrf_exempt
def bookings_create(request):
    if request.method != "POST":
        return json_error(405, "METHOD_NOT_ALLOWED")
    payload, err = read_payload(request)
    if err:
        return err
    body, berr = parse_body(request)
    if berr:
        return berr

    b = (body or {}).get("booking") or {}
    company_id = b.get("companyId")
    user = b.get("user") or {}
    appt_in = b.get("appointment") or {}
    phone = (user.get("phone") or "").strip()

    if (e := require_claim(payload, "companyId", company_id)):
        return e
    if (e := require_claim(payload, "userPhone", phone)):
        return e

    tenant = _resolve_company(company_id)
    if tenant is None:
        return json_error(404, "COMPANY_NOT_FOUND")

    service_ids = appt_in.get("serviceIds") or []
    resource_id = appt_in.get("resourceId")
    try:
        start = mappers.parse_dt(appt_in.get("datetime"))
    except (ValueError, TypeError):
        return json_error(422, "BAD_DATETIME", "Некорректное время")
    if not (service_ids and resource_id and phone):
        return json_error(422, "MISSING_FIELDS", "Нужны serviceIds, resourceId и телефон")

    with tenant_context(tenant):
        emp = Employee.objects.filter(pk=resource_id, is_active=True).first()
        if emp is None:
            return json_error(422, "RESOURCE_NOT_FOUND", "Мастер не найден")
        services = list(Service.objects.filter(id__in=service_ids, is_active=True))
        if not services:
            return json_error(422, "SERVICE_NOT_FOUND", "Услуга не найдена")

        total_min = sum((s.duration_min or 60) for s in services)
        if not is_slot_free(emp, start, total_min):
            return json_error(422, "SLOT_TAKEN", "Время уже занято")

        name = (f"{user.get('name', '')} {user.get('lastName', '')}").strip() or phone
        client, _ = Client.objects.get_or_create(phone=phone, defaults={"full_name": name})
        if name and not client.full_name:
            client.full_name = name
            client.save(update_fields=["full_name"])

        total_price = sum((s.price or Decimal("0")) for s in services)
        primary = services[0]
        with suppress():
            appt = Appointment.objects.create(
                client=client, employee=emp, service=primary, start=start,
                duration_min=total_min, price=total_price,
                status=Appointment.STATUS_WAIT,
                pdn_consent=True, comment=b.get("comment") or "Яндекс.Карты",
                source=Appointment.SOURCE_EXTERNAL, external_system="yandex",
            )
            appt.external_id = str(appt.id)
            appt.save(update_fields=["external_id"])
            for s in services:
                AppointmentService.objects.create(appointment=appt, service=s, price=s.price)

        return JsonResponse({"booking": mappers.booking_json(appt, service_ids)})


def _find_yandex_appt(booking_id):
    return (Appointment.all_objects
            .filter(external_id=str(booking_id), external_system="yandex")
            .select_related("tenant", "employee").first())


@csrf_exempt
def booking_detail(request, booking_id):
    payload, err = read_payload(request)
    if err:
        return err
    if (e := require_claim(payload, "bookingId", booking_id)):
        return e
    appt = _find_yandex_appt(booking_id)
    if appt is None:
        return json_error(404, "BOOKING_NOT_FOUND")
    tenant = appt.tenant

    if request.method == "GET":
        with tenant_context(tenant):
            service_ids = list(appt.lines.values_list("service_id", flat=True)) or [appt.service_id]
            return JsonResponse({"booking": mappers.booking_json(appt, service_ids)})

    if request.method == "PUT":
        body, berr = parse_body(request)
        if berr:
            return berr
        b = (body or {}).get("booking") or {}
        appt_in = b.get("appointment") or {}
        with tenant_context(tenant), suppress():
            if appt_in.get("datetime"):
                try:
                    appt.start = mappers.parse_dt(appt_in["datetime"])
                except (ValueError, TypeError):
                    return json_error(422, "BAD_DATETIME")
            if "comment" in b:
                appt.comment = b.get("comment") or ""
            appt.save(update_fields=["start", "comment"])
            service_ids = list(appt.lines.values_list("service_id", flat=True)) or [appt.service_id]
            return JsonResponse({"booking": mappers.booking_json(appt, service_ids)})

    if request.method == "DELETE":
        if appt.status == Appointment.STATUS_CAME:
            return json_error(422, "CANCEL_FORBIDDEN", "Визит уже состоялся")
        with tenant_context(tenant), suppress():
            appt.delete()
        return JsonResponse({})

    return json_error(405, "METHOD_NOT_ALLOWED")


# ---------------------------------------------------------------------------
# Предбронирование — не поддерживаем (валидно по спеке: 404)
# ---------------------------------------------------------------------------
@csrf_exempt
def prebookings_create(request):
    return json_error(404, "PREBOOKING_NOT_SUPPORTED")


@csrf_exempt
def prebooking_delete(request, prebooking_id):
    return json_error(404, "PREBOOKING_NOT_SUPPORTED")
