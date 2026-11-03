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

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-appointments",
            action="store_true",
            help="Дополнительно создать 3 демо-записи на сегодня (по умолчанию НЕ создаёт).",
        )

    def handle(self, *args, **options):
        self._with_appts = options.get("with_appointments", False)
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
        # Включаем модуль «Финансы» демо-тенанту (чтобы пункт был виден) + демо-биллинг
        from datetime import timedelta
        mods = set(tenant.enabled_modules or [])
        mods.add("finance")
        mods.add("stock")
        mods.add("subscriptions")
        mods.add("payroll")
        mods.add("booking")
        mods.add("yandex_booking")
        tenant.enabled_modules = sorted(mods)
        if not tenant.plan:
            tenant.plan = "Бизнес"
        if not tenant.paid_until:
            tenant.paid_until = timezone.localdate() + timedelta(days=30)
        if not tenant.acquiring_pct:
            tenant.acquiring_pct = 2  # демо: комиссия эквайринга 2%
        # Демо-данные точки для фида Яндекса (чтобы интеграцию можно было протестировать)
        if not tenant.address:
            tenant.yandex_permalink = tenant.yandex_permalink or "1124715036"
            tenant.address = "Россия, Москва, улица Ленина, 1"
            tenant.latitude = tenant.latitude or 55.755820
            tenant.longitude = tenant.longitude or 37.617633
            tenant.public_phone = tenant.public_phone or "+74950000000"
            tenant.yandex_rubric = tenant.yandex_rubric or "Салон красоты"
        tenant.save(update_fields=[
            "enabled_modules", "plan", "paid_until", "acquiring_pct",
            "yandex_permalink", "address", "latitude", "longitude",
            "public_phone", "yandex_rubric",
        ])
        self.stdout.write(("Создан" if created else "Уже есть") + f" тенант: {tenant.name}")

        # Провайдерский админ (control plane над всеми салонами), без тенанта
        provider, _ = User.objects.get_or_create(
            username="provider", defaults={"is_provider_admin": True, "tenant": None},
        )
        provider.is_provider_admin = True
        provider.tenant = None
        provider.set_password("demo12345")
        provider.save()
        self.stdout.write("  провайдер: provider / demo12345")

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

        # Склад: материалы + демо-техкарты (себестоимость → маржа)
        from stock.models import Material, TechCardItem
        mats_def = [
            # name, unit, qty, low, cost, waste_%
            ("Краска для волос", "мл", 2000, 300, 8, 5),
            ("Оксид", "мл", 3000, 500, 3, 5),
            ("Гель-лак", "мл", 500, 100, 20, 8),
            ("Пилочка одноразовая", "шт", 200, 30, 15, 10),
        ]
        mats = {}
        for mname, unit, qty, low, cost, waste in mats_def:
            m, _ = Material.objects.get_or_create(
                name=mname,
                defaults={"unit": unit, "quantity": qty, "low_threshold": low,
                          "cost_per_unit": cost, "waste_pct": waste},
            )
            mats[mname] = m
        techcards_def = [
            ("Окрашивание", [("Краска для волос", 60), ("Оксид", 90)]),
            ("Маникюр + гель-лак", [("Гель-лак", 5), ("Пилочка одноразовая", 1)]),
        ]
        for sname, lines in techcards_def:
            for mname, qty in lines:
                TechCardItem.objects.get_or_create(
                    service=services[sname], material=mats[mname], defaults={"qty": qty})
        self.stdout.write(f"  материалов: {len(mats)}, техкарт: {len(techcards_def)}")

        # Клиенты
        clients_def = [("Анна Кузнецова", "+79160000001"), ("Елена Волкова", "+79160000002"),
                       ("София Романова", "+79160000003")]
        clients = {}
        for cname, phone in clients_def:
            c, _ = Client.objects.get_or_create(phone=phone, defaults={"full_name": cname})
            clients[cname] = c

        # Абонементы/сертификаты: продукты + продажа демо-клиентам
        from subscriptions.models import ClientSubscription, SubscriptionPlan
        pkg, _ = SubscriptionPlan.objects.get_or_create(
            name="10 маникюров",
            defaults={"kind": SubscriptionPlan.VISITS, "service": services["Маникюр + гель-лак"],
                      "total_uses": 10, "price": 16000, "validity_days": 180},
        )
        cert, _ = SubscriptionPlan.objects.get_or_create(
            name="Сертификат 5000",
            defaults={"kind": SubscriptionPlan.MONEY, "value": 5500, "price": 5000, "validity_days": 365},
        )
        if not ClientSubscription.objects.exists():
            ClientSubscription.objects.create(
                client=clients["Елена Волкова"], plan=cert, name=cert.name,
                kind=cert.kind, balance=cert.value, status=ClientSubscription.ACTIVE)
            ClientSubscription.objects.create(
                client=clients["Анна Кузнецова"], plan=pkg, name=pkg.name,
                kind=pkg.kind, service=pkg.service, remaining_uses=pkg.total_uses,
                status=ClientSubscription.ACTIVE)
            self.stdout.write("  абонементов продано: 2")

        # Зарплаты: схема (оклад + прогрессивные пороги) и назначение мастерам
        from payroll.models import PayrollScheme, PayrollTier
        scheme, created_s = PayrollScheme.objects.get_or_create(
            name="Мастер · стандарт", defaults={"base_per_day": 1500})
        if created_s:
            for mn, pct in [(0, 30), (15000, 40), (30000, 50)]:
                PayrollTier.objects.create(scheme=scheme, min_revenue=mn, pct=pct)
        for e in employees.values():
            if e.payroll_scheme_id is None:
                e.payroll_scheme = scheme
                e.save(update_fields=["payroll_scheme"])
        self.stdout.write("  схема ЗП назначена мастерам")

        # Записи на сегодня — ТОЛЬКО по флагу --with-appointments.
        # Иначе команду можно безопасно гонять на рабочей базе: она не подкинет
        # «левых» записей в журнал.
        if not getattr(self, "_with_appts", False):
            self.stdout.write("  демо-записи пропущены (запусти с --with-appointments, чтобы создать)")
            return
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
