"""Снятие вебхука Telegram (например, чтобы вернуться на polling)."""
from django.core.management.base import BaseCommand

from core.models import Tenant
from core.tenancy import tenant_context
from notifications import telegram as tg
from notifications.service import get_settings


class Command(BaseCommand):
    help = "Снимает вебхук Telegram у тенантов."

    def add_arguments(self, parser):
        parser.add_argument("--slug", help="Только для одного тенанта (slug)")

    def handle(self, *args, **options):
        q = Tenant.objects.filter(is_active=True)
        if options.get("slug"):
            q = q.filter(slug=options["slug"])
        for t in q:
            with tenant_context(t):
                token = get_settings().telegram_bot_token
            if not token:
                continue
            res = tg.delete_webhook(token)
            self.stdout.write(f"  {t.slug}: {'OK' if res.get('ok') else res.get('description', 'ошибка')}")
