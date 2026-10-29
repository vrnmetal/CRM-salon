"""
Демо-данные для первого запуска: один тенант, роли из пресетов, по пользователю
на роль. Чтобы сразу увидеть работающий каркас (вход, роутинг по роли, доступы).

Запуск:  python manage.py seed_demo
Пароль у всех демо-пользователей: demo12345
"""
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from appointments.models import Appointment, AppointmentService, Service, ServiceCategory
from clients.models import Client
from core.models import Role, Tenant, User
from core.permissions import role_presets
from core.tenancy import tenant_context
from staff.models import Employee


class Command(BaseCommand):
    help = "Создаёт демо-тенанта, роли из пресетов и демо-пользователей."

    def handle(self, *args, **options):
        # --- Тенант ---
        tenant, created = Tenant.objects.get_or_create(
            slug="demo",
            defaults={
                "name": "Демо-салон",
                "brand_name": "Studio Demo",
                "accent_color": "#B97A64",  # тёплая терракота как пример акцента
                "is_active": True,
            },
        )
        # Включаем модуль «Финансы» демо-тенанту (чтобы пункт был виден)
        mods = set(tenant.enabled_modules or [])
        if "finance" not in mods:
            mods.add("finance")
            tenant.enabled_modules = sorted(mods)
            tenant.save(update_fields=["enabled_modules"])
        self.stdout.write(("Создан" if created else "Уже есть") + f" тенант: {tenant.name}")

        # --- Роли из пресетов ---
        presets = role_presets()
        roles = {}
        for code, preset in presets.items():
            role, _ = Role.objects.update_or_create(
                tenant=tenant,
                name=preset["name"],
                defaults={"preset_code": code, "permission_codes": preset["codes"]},
            )
            roles[code] = role
            self.stdout.write(f"  роль «{role.name}»: прав {len(preset['codes'])}")

        # --- Пользователи: по одному на роль ---
        demo = [
            ("owner", "owner"),
            ("admin", "admin"),
            ("master", "master"),
        ]
        for username, role_code in demo:
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={"tenant": tenant, "role": roles[role_code]},
            )
            user.tenant = tenant
            user.role = roles[role_code]
            # Права КОПИРУЕМ из пресета роли на аккаунт (роль — лишь заготовка галочек)
            user.permission_codes = list(roles[role_code].permission_codes or [])
            user.set_password("demo12345")
            user.save()
            self.stdout.write(f"  пользователь {username} / demo12345 ({roles[role_code].name})")

        # --- Бизнес-данные (мастера, услуги, клиенты, записи на сегодня) ---
        # Работаем в контексте тенанта, чтобы objects/дедуп находили существующее.
        with tenant_context(tenant):
            self._seed_business(tenant)

        self.stdout.write(self.style.SUCCESS("Готово. Вход: owner|admin|master, пароль demo12345."))

    def _seed_business(self, tenant):
        # Мастера — колонки журнала
        # work_days: 0=Пн … 6=Вс. Пусто = каждый день.
        masters = [
            ("Мария", "Стилист-парикмахер", "#B5651D", 10, [0, 1, 2, 3, 4]),   # будни
            ("Ольга", "Мастер маникюра", "#6A5ACD", 20, [2, 3, 4, 5, 6]),      # ср–вс
            ("Иван", "Массажист", "#1C8C4A", 30, [0, 2, 4]),                    # пн/ср/пт
        ]
        employees = {}
        for name, spec, color, order, wdays in masters:
            e, _ = Employee.objects.get_or_create(
                full_name=name,
                defaults={"specialization": spec, "color": color,
                          "sort_order": order, "work_days": wdays},
            )
            employees[name] = e
        self.stdout.write(f"  мастеров: {len(employees)}")

        # Категории + услуги (с длительностью и ценой)
        cat_hair, _ = ServiceCategory.objects.get_or_create(name="Волосы", defaults={"sort_order": 10})
        cat_nails, _ = ServiceCategory.objects.get_or_create(name="Ногти", defaults={"sort_order": 20})
        cat_body, _ = ServiceCategory.objects.get_or_create(name="Тело", defaults={"sort_order": 30})
        services_def = [
            ("Окрашивание", cat_hair, 120, 4200),
            ("Стрижка", cat_hair, 60, 1800),
            ("Маникюр + гель-лак", cat_nails, 90, 2000),
            ("Классический массаж", cat_body, 60, 3500),
        ]
        services = {}
        for name, cat, dur, price in services_def:
            s, _ = Service.objects.get_or_create(
                name=name, defaults={"category": cat, "duration_min": dur, "price": price},
            )
            services[name] = s
        self.stdout.write(f"  услуг: {len(services)}")

        # Клиенты
        clients_def = [("Анна Кузнецова", "+79160000001"), ("Елена Волкова", "+79160000002"),
                       ("София Романова", "+79160000003")]
        clients = {}
        for cname, phone in clients_def:
            c, _ = Client.objects.get_or_create(phone=phone, defaults={"full_name": cname})
            clients[cname] = c

        # Записи на сегодня (если ещё не создавали)
        today = timezone.localdate()
        if not Appointment.objects.filter(start__date=today).exists():
            plan = [
                ("Анна Кузнецова", "Мария", "Окрашивание", time(10, 0), Appointment.STATUS_CAME),
                ("Елена Волкова", "Ольга", "Маникюр + гель-лак", time(11, 30), Appointment.STATUS_WAIT),
                ("София Романова", "Иван", "Классический массаж", time(13, 0), Appointment.STATUS_CONFIRMED),
            ]
            for cname, mname, sname, t, status in plan:
                svc = services[sname]
                start = timezone.make_aware(datetime.combine(today, t))
                appt = Appointment.objects.create(
                    client=clients[cname], employee=employees[mname], service=svc,
                    start=start, duration_min=svc.duration_min, price=svc.price,
                    status=status, pdn_consent=True,
                )
                AppointmentService.objects.create(appointment=appt, service=svc, price=svc.price)
            self.stdout.write("  записей на сегодня: 3")
