"""
Опрос Telegram-бота (polling) — связывание chat_id клиентов БЕЗ публичного домена.
Для пилота. Запуск по cron (например, раз в минуту) или вручную:

    */1 * * * * cd /home/<user>/salon && .venv/bin/python manage.py telegram_poll
"""
from django.core.management.base import BaseCommand

from core.models import Tenant
from core.tenancy import tenant_context
from notifications import telegram as tg
from notifications.service import get_settings


class Command(BaseCommand):
    help = "Забирает апдейты Telegram-ботов тенантов (polling) и связывает chat_id клиентов."

    def add_arguments(self, parser):
        parser.add_argument("--slug", help="Только для одного тенанта (slug)")

    def handle(self, *args, **options):
        q = Tenant.objects.filter(is_active=True)
        if options.get("slug"):
            q = q.filter(slug=options["slug"])
        for t in q:
            with tenant_context(t):
                s = get_settings()
                token = s.telegram_bot_token
                if not token:
                    continue
                offset = s.telegram_poll_offset or 0
                res = tg.get_updates(token, offset=offset + 1 if offset else None, timeout=0)
                if not res.get("ok"):
                    self.stdout.write(f"  {t.slug}: {res.get('description', 'ошибка')}")
                    continue
                ups = res.get("result", [])
                for u in ups:
                    tg.handle_update(token, u)
                    s.telegram_poll_offset = u["update_id"]
                if ups:
                    s.save(update_fields=["telegram_poll_offset"])
                self.stdout.write(f"  {t.slug}: обработано апдейтов {len(ups)}")
