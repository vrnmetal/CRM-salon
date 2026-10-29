"""
Движок прав: permission-first, deny-by-default.

Правило проекта: КАЖДОЕ изменяющее действие регистрирует здесь свой атомарный
permission ОДНОВРЕМЕННО с кодом действия. Право, которого нет в реестре, не
существует → действие запрещено. Роли — это пресеты-наборы кодов поверх реестра.
UI «Настройки доступа» строится из этого реестра автоматически.

Гранулярность живёт в движке (право на каждое действие/чувствительное поле),
а в интерфейсе права группируются по разделам (section) + выдаются пресетами,
чтобы собственник не тонул в сотнях галочек.
"""
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied

from core.modules import is_module_enabled


@dataclass(frozen=True)
class Permission:
    code: str      # атомарный код, например "appointment.create"
    label: str     # человекочитаемое описание для UI
    module: str    # к какому модулю относится (для гейтинга + группировки)
    section: str   # раздел в UI настроек доступа


# Единый реестр прав
REGISTRY: dict[str, Permission] = {}


def register(code: str, label: str, module: str, section: str) -> str:
    # Повторная регистрация того же кода — ошибка проектирования, ловим сразу.
    if code in REGISTRY:
        raise ValueError(f"Право уже зарегистрировано: {code}")
    REGISTRY[code] = Permission(code=code, label=label, module=module, section=section)
    return code


# ============================================================================
# Регистрация прав ядра. Каждое новое изменяющее действие в модулях будет
# добавлять свой register(...) РЯДОМ со своим кодом (а не задним числом).
# ============================================================================

# --- Записи и журнал ---
register("appointment.view", "Видеть журнал записей", "appointments", "Записи")
register("appointment.create", "Создавать запись", "appointments", "Записи")
register("appointment.edit", "Изменять запись", "appointments", "Записи")
register("appointment.cancel", "Отменять запись", "appointments", "Записи")
register("appointment.delete", "Удалять запись", "appointments", "Записи")

# --- Клиенты ---
register("client.view", "Видеть клиентов", "clients", "Клиенты")
register("client.create", "Создавать клиента", "clients", "Клиенты")
register("client.edit", "Изменять клиента", "clients", "Клиенты")
# Чувствительное поле: телефон клиента (анти-увод базы — скрываем от мастеров)
register("client.phone.view", "Видеть телефон клиента", "clients", "Клиенты")

# --- Сотрудники и график ---
register("staff.view", "Видеть сотрудников", "staff", "Сотрудники")
register("staff.create", "Создавать сотрудника", "staff", "Сотрудники")
register("staff.edit", "Изменять сотрудника", "staff", "Сотрудники")
register("staff.schedule.edit", "Менять график работы", "staff", "Сотрудники")

# --- Услуги ---
register("service.view", "Видеть услуги", "appointments", "Услуги")
register("service.create", "Создавать услугу", "appointments", "Услуги")
register("service.edit", "Изменять услугу", "appointments", "Услуги")

# --- Дашборд ---
register("dashboard.view", "Видеть дашборд собственника", "dashboard", "Аналитика")

# --- Системные (всегда доступны при наличии права, без гейтинга по модулю) ---
register("access.manage", "Настраивать доступы (роли и права)", "system", "Администрирование")
register("account.manage", "Создавать и удалять аккаунты", "system", "Администрирование")
register("branding.manage", "Настраивать брендирование", "system", "Администрирование")

# --- Провайдерский слой (только is_provider_admin) ---
register("provider.tenants.view", "Видеть список тенантов", "provider", "Провайдер")
register("provider.tenant.toggle", "Включать/выключать тенанта", "provider", "Провайдер")
register("provider.impersonate", "Входить как клиент (impersonate)", "provider", "Провайдер")


# ============================================================================
# Проверка права
# ============================================================================
def has_perm(user, code: str) -> bool:
    # Неаутентифицированный — ничего нельзя
    if not getattr(user, "is_authenticated", False):
        return False
    # Суперюзер (разработчик/владелец системы) — всё можно
    if getattr(user, "is_superuser", False):
        return True

    perm = REGISTRY.get(code)
    if perm is None:
        # Неизвестное право — запрещаем (deny-by-default на уровне реестра)
        return False

    # Провайдерские права — только провайдерскому админу
    if perm.module == "provider":
        return bool(getattr(user, "is_provider_admin", False))

    # Гейтинг по модулю тенанта (system — не гейтим; ядро/модули — по флагам сборки)
    if perm.module != "system":
        if not is_module_enabled(getattr(user, "tenant", None), perm.module):
            return False

    # Наконец — есть ли код в ПЕРСОНАЛЬНОМ наборе аккаунта (deny-by-default).
    # Права хранятся на пользователе; роль — лишь пресет, с которого они копируются.
    return code in (getattr(user, "permission_codes", None) or [])


# ============================================================================
# Декоратор для вьюх: защита действия на СЕРВЕРЕ (не только пряча кнопку в UI)
# ============================================================================
def requires(code: str):
    def decorator(view_func):
        def wrapped(request, *args, **kwargs):
            if not has_perm(request.user, code):
                raise PermissionDenied(f"Нет права: {code}")
            return view_func(request, *args, **kwargs)
        wrapped.__name__ = getattr(view_func, "__name__", "wrapped")
        wrapped.__doc__ = view_func.__doc__
        # Помечаем вьюху требуемым правом — пригодится для скрипта-проверки покрытия
        wrapped._required_permission = code
        return wrapped
    return decorator


def requires_any(*codes: str):
    """Доступ, если есть ХОТЯ БЫ ОДНО из прав (напр. раздел настроек)."""
    def decorator(view_func):
        def wrapped(request, *args, **kwargs):
            if not any(has_perm(request.user, c) for c in codes):
                raise PermissionDenied(f"Нет ни одного из прав: {codes}")
            return view_func(request, *args, **kwargs)
        wrapped.__name__ = getattr(view_func, "__name__", "wrapped")
        wrapped.__doc__ = view_func.__doc__
        # Для скрипта-проверки: отметим первым из кодов (достаточно для «вьюха защищена»)
        wrapped._required_permission = codes[0]
        return wrapped
    return decorator


# ============================================================================
# Пресеты ролей: из чего засеваются роли нового тенанта. Собственник получает
# все права включённых модулей; остальные — подмножества.
# ============================================================================
def _codes_for_modules(modules: set[str]) -> list[str]:
    # Все коды прав из указанных модулей (+ системные для собственника добавим отдельно)
    return [p.code for p in REGISTRY.values() if p.module in modules]


def role_presets() -> dict[str, dict]:
    """Возвращает пресеты ролей (пересчитываются из актуального реестра)."""
    owner_codes = [
        p.code for p in REGISTRY.values() if p.module not in ("provider",)
    ]
    admin_codes = _codes_for_modules({"appointments", "clients"}) + [
        "staff.view",
        "dashboard.view",
    ]
    master_codes = [
        "appointment.view",
        "client.view",
    ]
    return {
        "owner": {"name": "Собственник", "codes": owner_codes},
        "admin": {"name": "Администратор", "codes": admin_codes},
        "master": {"name": "Мастер", "codes": master_codes},
    }
