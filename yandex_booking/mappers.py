"""
Преобразование наших моделей в JSON-формат Maps Booking API и обратно.

Форматы — по публичной спецификации Яндекса (точные имена полей: title,
durationSeconds, price.range, datetime в UTC с Z). Точки, помеченные
[СВЕРИТЬ], финально подтверждаются на тестовом контуре Яндекса.
"""
from datetime import datetime, timezone as dt_timezone

from django.utils import timezone


# ---- datetime ----
def to_utc_iso(dt) -> str:
    """aware datetime → '2026-11-03T08:48:00.000Z' (UTC)."""
    return dt.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def parse_dt(value):
    """ISO-строка Яндекса (возможно с 'Z') → aware datetime в локальной TZ проекта."""
    s = (value or "").replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return timezone.localtime(dt)


# ---- модели → JSON ----
def company_json(tenant, base_url: str) -> dict:
    coords = None
    if tenant.latitude is not None and tenant.longitude is not None:
        coords = {"lat": float(tenant.latitude), "lon": float(tenant.longitude)}
    return {
        "id": tenant.slug,                       # наш идентификатор компании (companyId)
        "permalink": tenant.yandex_permalink or "",  # ключ сопоставления с карточкой
        "name": tenant.brand_name or tenant.name,
        "address": tenant.address or "",
        "coordinates": coords,
        "phones": [tenant.public_phone] if tenant.public_phone else [],
        "urls": [],
        "bookingUrl": f"{base_url}/book/{tenant.slug}/",
        "services": [],                          # детально — через /services
        "resources": [],                         # детально — через /resources
        "rubrics": [tenant.yandex_rubric] if tenant.yandex_rubric else ["Салон красоты"],
        "isPaymentSupported": False,             # онлайн-предоплаты в записи нет
    }


def service_json(service, employees) -> dict:
    price = int(service.price or 0)
    # У нас нет матрицы услуга↔мастер, поэтому услугу могут оказывать все активные
    # мастера с её длительностью. [СВЕРИТЬ] — при необходимости сузить.
    resources = [
        {"id": str(e.id), "durationSeconds": (service.duration_min or 60) * 60}
        for e in employees
    ]
    return {
        "id": str(service.id),
        "title": service.name,
        "description": "",
        "category": service.category.name if service.category_id else "",
        "image": "",
        "price": {"currencyCode": "RUB", "range": [price, price]},
        "durationSeconds": (service.duration_min or 60) * 60,
        "resources": resources,
    }


def resource_json(employee) -> dict:
    return {
        "id": str(employee.id),
        "title": employee.full_name,
        "description": employee.specialization or "",
        "information": "",
        "rating": 0,
        "image": "",
        "reviewsCount": 0,
    }


def booking_json(appt, service_ids) -> dict:
    return {
        "id": appt.external_id or str(appt.id),
        "status": "created",
        "serviceIds": [str(s) for s in service_ids],
        "resourceId": str(appt.employee_id),
        "datetime": to_utc_iso(appt.start),
        "comment": appt.comment or "",
        "paidAmount": 0,
    }
