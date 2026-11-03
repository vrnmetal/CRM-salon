"""
TOTP (RFC 6238) на стандартной библиотеке — без внешних зависимостей.
Совместимо с Google Authenticator и аналогами (SHA1, 6 цифр, шаг 30 сек).
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def generate_secret(length=20):
    """Случайный секрет, кодированный в base32 (как ждёт аутентификатор)."""
    raw = secrets.token_bytes(length)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _hotp(secret_b32, counter):
    # Восстанавливаем padding base32 и считаем HOTP-код
    pad = "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(secret_b32.upper() + pad)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def verify(secret_b32, code, window=1, step=30):
    """Проверка кода с допуском ±window шагов (на рассинхрон часов)."""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    counter = int(time.time() // step)
    for drift in range(-window, window + 1):
        if hmac.compare_digest(_hotp(secret_b32, counter + drift), code):
            return True
    return False


def provisioning_uri(secret_b32, account_name, issuer="Salon CRM"):
    """otpauth://-ссылка для QR-кода."""
    label = quote(f"{issuer}:{account_name}")
    params = f"secret={secret_b32}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    return f"otpauth://totp/{label}?{params}"
