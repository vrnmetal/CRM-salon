"""
Авто-отправка напоминаний. Запускается планировщиком (cron) раз в N минут:

    */10 * * * * cd /home/<user>/salon && .venv/bin/python manage.py send_due_reminders

Проходит по всем активным тенантам; у кого включён авто-режим — шлёт напоминания
всем записям, которым пора. Идемпотентно: повторный запуск не задваивает.
"""
from django.core.management.base import BaseCommand

from core.models import Tenant
from core.tenancy import tenant_context
from notifications.service import process_tenant_auto


class Command(BaseCommand):
    help = "Отправляет авто-напоминания о визитах всем тенантам с включённым авто-режимом."

    def handle(self, *args, **options):
        total = 0
        tenants = 0
        for t in Tenant.objects.filter(is_active=True):
            with tenant_context(t):
                sent = process_tenant_auto()
            if sent:
                tenants += 1
                total += sent
                self.stdout.write(f"  {t.slug}: отправлено {sent}")
        self.stdout.write(self.style.SUCCESS(
            f"Готово. Напоминаний отправлено: {total} (тенантов затронуто: {tenants})"))
