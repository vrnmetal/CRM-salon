"""
Минимальная реализация JWT (HS256) на стандартной библиотеке — без PyJWT.

Яндекс подписывает входящие токены общим секретом (его выдаёт Яндекс при
подключении). Мы проверяем подпись этим же секретом. Для обратных вызовов к
Яндексу мы сами подписываем токен тем же секретом.
"""
import base64
import hashlib
import hmac
import json
import time


def _b64url(raw: bytes) -> bytes:
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def _b64url_decode(seg: str) -> bytes:
    pad = "=" * (-len(seg) % 4)
    return base64.urlsafe_b64decode(seg + pad)


def encode(payload: dict, secret: str, exp_seconds: int = 300) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    body = dict(payload)
    now = int(time.time())
    body.setdefault("iat", now)
    body.setdefault("exp", now + exp_seconds)
    segs = [
        _b64url(json.dumps(header, separators=(",", ":")).encode()),
        _b64url(json.dumps(body, separators=(",", ":")).encode()),
    ]
    signing_input = b".".join(segs)
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    segs.append(_b64url(sig))
    return b".".join(segs).decode()


def decode(token: str, secret: str, verify_exp: bool = True) -> dict:
    """Проверяет подпись и (если есть) exp. Бросает ValueError при любой проблеме."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("malformed token")
    signing_input = (parts[0] + "." + parts[1]).encode()
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    try:
        given = _b64url_decode(parts[2])
    except Exception as e:  # noqa: BLE001
        raise ValueError("bad signature encoding") from e
    if not hmac.compare_digest(given, expected):
        raise ValueError("signature mismatch")
    payload = json.loads(_b64url_decode(parts[1]))
    if verify_exp and "exp" in payload and int(time.time()) > int(payload["exp"]):
        raise ValueError("token expired")
    return payload
