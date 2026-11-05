"""
Драйверы каналов отправки — абстракция (как у платежей): канал подключается
плагином без переписывания логики. Каждый .send(recipient, text) возвращает
{"ok","external_id","error"}. recipient — это Client (или None).

По умолчанию канал console (пишет в лог, считается отправленным) — чтобы гонять
весь цикл без реального канала. Telegram шлёт по-настоящему, если клиент подписан
на бота (есть telegram_chat_id).
"""
import logging

from notifications import telegram as tg

log = logging.getLogger("notifications")


class BaseDriver:
    code = "base"

    def __init__(self, settings):
        self.settings = settings

    def send(self, recipient, text):
        raise NotImplementedError


class ConsoleDriver(BaseDriver):
    code = "console"

    def send(self, recipient, text):
        who = getattr(recipient, "phone", "") or "?"
        log.info("[notify stub] → %s: %s", who, text)
        return {"ok": True, "external_id": "", "error": ""}


class TelegramDriver(BaseDriver):
    code = "telegram"

    def send(self, recipient, text):
        token = self.settings.telegram_bot_token
        if not token:
            return {"ok": False, "external_id": "", "error": "Не задан токен Telegram-бота"}
        chat_id = getattr(recipient, "telegram_chat_id", "") if recipient else ""
        if not chat_id:
            return {"ok": False, "external_id": "",
                    "error": "Клиент не подписан на бота (нет chat_id)"}
        res = tg.send_message(token, chat_id, text)
        if res.get("ok"):
            mid = str((res.get("result") or {}).get("message_id", ""))
            return {"ok": True, "external_id": mid, "error": ""}
        return {"ok": False, "external_id": "",
                "error": res.get("description", "Ошибка Telegram")}


class SmsDriver(BaseDriver):
    """SMS через агрегатора. Пока поддержан SMSC.ru (модель A: аккаунт салона).
    Эндпоинт/параметры — по докам SMSC [СВЕРИТЬ на реальном аккаунте]."""
    code = "sms"

    def send(self, recipient, text):
        import json
        import urllib.parse
        import urllib.request

        s = self.settings
        phone = (getattr(recipient, "phone", "") or "") if recipient else ""
        if not (s.sms_login and s.sms_password):
            return {"ok": False, "external_id": "", "error": "SMS-провайдер не настроен"}
        if not phone:
            return {"ok": False, "external_id": "", "error": "У клиента нет телефона"}

        params = {
            "login": s.sms_login, "psw": s.sms_password,
            "phones": phone, "mes": text, "fmt": 3, "charset": "utf-8",
        }
        if s.sms_sender:
            params["sender"] = s.sms_sender
        url = "https://smsc.ru/sys/send.php?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310
                res = json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "external_id": "", "error": str(e)}
        if isinstance(res, dict) and res.get("error"):
            return {"ok": False, "external_id": "", "error": str(res.get("error"))}
        return {"ok": True, "external_id": str((res or {}).get("id", "")), "error": ""}


class EmailDriver(BaseDriver):
    code = "email"

    def send(self, recipient, text):
        return {"ok": False, "external_id": "", "error": "Email-канал не настроен"}


_DRIVERS = {
    ConsoleDriver.code: ConsoleDriver,
    TelegramDriver.code: TelegramDriver,
    SmsDriver.code: SmsDriver,
    EmailDriver.code: EmailDriver,
}


def get_driver(settings):
    cls = _DRIVERS.get(settings.channel, ConsoleDriver)
    return cls(settings)
