"""
Тонкий клиент Telegram Bot API (stdlib) + логика бота для подписки клиентов.

Ограничение Telegram: бот НЕ может написать пользователю по номеру — клиент должен
сам открыть бота и поделиться контактом. Тогда мы сопоставляем его телефон с
карточкой клиента и сохраняем chat_id, по которому потом шлём напоминания.

Связывание chat_id работает двумя способами (на выбор по инфраструктуре):
  • webhook — боту шлёт апдейты наш публичный URL (нужен HTTPS-домен);
  • polling — команда telegram_poll периодически забирает апдейты (без домена, для пилота).
"""
import hashlib
import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger("notifications")

_API = "https://api.telegram.org/bot{token}/{method}"


def _call(token, method, payload=None, timeout=10):
    url = _API.format(token=token, method=method)
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"ok": False, "description": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "description": str(e)}


def send_message(token, chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return _call(token, "sendMessage", payload)


def get_me(token):
    return _call(token, "getMe", timeout=8)


def get_updates(token, offset=None, timeout=0):
    payload = {"timeout": timeout}
    if offset:
        payload["offset"] = offset
    return _call(token, "getUpdates", payload, timeout=timeout + 10)


def webhook_secret(token):
    """Детерминированный секрет вебхука из токена — сверяем заголовок от Telegram."""
    return hashlib.sha256(("wh:" + (token or "")).encode()).hexdigest()[:32]


def set_webhook(token, url):
    return _call(token, "setWebhook", {"url": url, "secret_token": webhook_secret(token)})


def delete_webhook(token):
    return _call(token, "deleteWebhook", {})


# ---------------------------------------------------------------------------
# Логика бота: подписка клиента (вызывается и из webhook, и из polling).
# Выполняется в tenant_context нужного салона (обеспечивает вызывающий код).
# ---------------------------------------------------------------------------
def link_contact(phone, chat_id):
    """Находит клиента по телефону (в любом формате) и сохраняет его chat_id."""
    from clients.models import Client
    from core.health import normalize_phone

    nat = normalize_phone(phone)
    if not nat:
        return None
    variants = ["+7" + nat, "7" + nat, "8" + nat, nat]
    client = Client.objects.filter(phone__in=variants).first()
    if client is None:
        return None
    client.telegram_chat_id = str(chat_id)
    client.save(update_fields=["telegram_chat_id"])
    return client


def handle_update(token, update):
    """Обрабатывает один апдейт: /start → просим контакт; контакт → связываем."""
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id:
        return
    contact = msg.get("contact")
    text = (msg.get("text") or "")

    if contact and contact.get("phone_number"):
        client = link_contact(contact["phone_number"], chat_id)
        if client:
            send_message(token, chat_id,
                         "Готово! Будем присылать напоминания о визитах.",
                         reply_markup={"remove_keyboard": True})
        else:
            send_message(token, chat_id,
                         "Не нашли ваш номер в базе салона. Обратитесь к администратору.",
                         reply_markup={"remove_keyboard": True})
    elif text.startswith("/start"):
        kb = {
            "keyboard": [[{"text": "📱 Поделиться номером", "request_contact": True}]],
            "resize_keyboard": True, "one_time_keyboard": True,
        }
        send_message(token, chat_id,
                     "Здравствуйте! Поделитесь номером телефона, чтобы получать "
                     "напоминания о визитах.", reply_markup=kb)
