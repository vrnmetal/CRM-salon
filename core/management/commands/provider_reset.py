"""
Восстановление провайдерского доступа С СЕРВЕРА (когда заперт снаружи).

Создаёт или сбрасывает провайдерский админ-аккаунт (tenant=None, is_provider_admin).
UI тут не поможет — это аварийный вход через консоль, доступную только владельцу
сервера. Поэтому держи бэкап-провайдера и не теряй доступ к серверу.

Примеры:
  python manage.py provider_reset provider --password НовыйПароль
  python manage.py provider_reset backup         # пароль сгенерируется и покажется
"""
import secrets

from django.core.management.base import BaseCommand

from core.models import User


class Command(BaseCommand):
    help = "Создать или сбросить провайдерский админ-аккаунт (аварийное восстановление доступа)."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Логин провайдерского аккаунта")
        parser.add_argument("--password", default=None, help="Новый пароль (если не задан — сгенерируется)")

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"] or secrets.token_urlsafe(10)

        user, created = User.objects.get_or_create(
            username=username, defaults={"is_provider_admin": True, "tenant": None},
        )
        user.is_provider_admin = True
        user.tenant = None
        user.set_password(password)
        # Сбрасываем 2FA — доступ к серверу остаётся абсолютным ключом восстановления
        user.totp_enabled = False
        user.totp_secret = ""
        user.backup_codes = []
        user.save()

        self.stdout.write(self.style.SUCCESS(f"{'Создан' if created else 'Обновлён'} провайдер: {username} (2FA сброшена)"))
        self.stdout.write(f"Пароль: {password}")
        self.stdout.write("Войди на сайте этим логином/паролем и сразу смени пароль.")
