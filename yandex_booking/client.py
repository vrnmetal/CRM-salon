"""
Обратная синхронизация: когда запись, пришедшую из Яндекса, меняют/отменяют
внутри нашего журнала, уведомляем Яндекс, чтобы обновить её в ЛК клиента в Картах.

PUT https://partner.maps.yandex.net/booking/v1/partners/{partnerId}/{bookingId}

Тело и способ авторизации в публичной спецификации не детализированы —
реализовано по общей логике API (Bearer JWT, подписанный нашим секретом).
[СВЕРИТЬ на тестовом контуре Яндекса] — формат тела и авторизацию.
Любая сетевая ошибка гасится и логируется: журнал салона работает независимо.
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

from yandex_booking import jwt
from yandex_booking.mappers import to_utc_iso

log = logging.getLogger("yandex_booking")


def _enabled() -> bool:
    return bool(settings.YANDEX_BOOKING_SECRET and settings.YANDEX_BOOKING_PARTNER_ID)


def push_booking_update(appt, status: str):
    """Отправляет изменение записи в Яндекс. appt — наш Appointment из Яндекса."""
    if not _enabled():
        return
    booking_id = appt.external_id or str(appt.id)
    url = (
        f"{settings.YANDEX_BOOKING_API_BASE}/booking/v1/partners/"
        f"{settings.YANDEX_BOOKING_PARTNER_ID}/{booking_id}"
    )
    body = {
        "booking": {
            "id": booking_id,
            "status": status,                       # [СВЕРИТЬ] набор статусов Яндекса
            "datetime": to_utc_iso(appt.start),
        }
    }
    token = jwt.encode({"bookingId": booking_id}, settings.YANDEX_BOOKING_SECRET)
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            resp.read()
    except (urllib.error.URLError, TimeoutError) as e:
        log.warning("Яндекс: не удалось синхронизировать запись %s: %s", booking_id, e)
