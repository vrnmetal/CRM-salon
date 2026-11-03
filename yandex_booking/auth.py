"""
Аутентификация входящих вызовов Яндекса по JWT (Bearer) + проверка claim'ов.

Пока секрет не задан (нет подключения) — любой вызов получает 503. Это намеренно:
до одобрения заявки Яндексом API не должен принимать записи.
"""
import json

from django.conf import settings
from django.http import JsonResponse

from yandex_booking import jwt


def json_error(status, code, message=""):
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def read_payload(request):
    """Возвращает (payload, error_response). Если error_response не None — вернуть его."""
    secret = settings.YANDEX_BOOKING_SECRET
    if not secret:
        return None, json_error(503, "NOT_CONFIGURED", "Интеграция ещё не подключена")
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None, json_error(401, "NO_TOKEN", "Нужен Bearer-токен")
    token = auth[len("Bearer "):].strip()
    try:
        payload = jwt.decode(token, secret)
    except ValueError:
        return None, json_error(401, "BAD_TOKEN", "Некорректный токен")
    return payload, None


def require_claim(payload, key, expected):
    """Проверяет, что claim payload[key] совпадает с ожидаемым значением запроса."""
    if str(payload.get(key, "")) != str(expected):
        return json_error(403, "CLAIM_MISMATCH", f"Поле {key} не совпадает")
    return None


def parse_body(request):
    try:
        return json.loads(request.body or b"{}"), None
    except (ValueError, TypeError):
        return None, json_error(422, "BAD_BODY", "Некорректный JSON")
