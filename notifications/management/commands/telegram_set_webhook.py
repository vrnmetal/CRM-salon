"""
Установка вебхука Telegram (прод-способ, нужен публичный HTTPS-домен):

    python manage.py telegram_set_webhook --base https://crm.example.ru --slug demo

Поставит боту тенанта вебхук на https://<base>/tg/<slug>/ с секретным заголовком.
Без --slug ставит всем активным тенантам с заданным токеном.
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import Tenant
from core.tenancy import tenant_context
from notifications import telegram as tg
from notifications.service import get_settings


class Command(BaseCommand):
    help = "Ставит вебхук Telegram на публичный URL тенанта."

    def add_arguments(self, parser):
        parser.add_argument("--base", required=True, help="Публичный базовый URL, напр. https://crm.example.ru")
        parser.add_argument("--slug", help="Только для одного тенанта (slug)")

    def handle(self, *args, **options):
        base = options["base"].rstrip("/")
        if not base.startswith("https://"):
            raise CommandError("Telegram требует HTTPS: base должен начинаться с https://")
        q = Tenant.objects.filter(is_active=True)
        if options.get("slug"):
            q = q.filter(slug=options["slug"])
        for t in q:
            with tenant_context(t):
                token = get_settings().telegram_bot_token
            if not token:
                continue
            url = f"{base}/tg/{t.slug}/"
            res = tg.set_webhook(token, url)
            ok = "OK" if res.get("ok") else res.get("description", "ошибка")
            self.stdout.write(f"  {t.slug}: {url} → {ok}")
