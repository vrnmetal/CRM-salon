"""
Реестр модулей продукта — основа модульной сборки.

Клиент покупает сборку = набор включённых модулей. Ядровые (is_core=True) включены
всегда; остальные — по флагу на тенанте (Tenant.enabled_modules).

Модуль может принести свой urls.py (поле urlconf) — тогда корневой config/urls.py
примонтирует его маршруты. Пока фич нет, urlconf у всех None: ядро обслуживается
напрямую через core/urls.py.
"""
from dataclasses import dataclass, field
from importlib import import_module


@dataclass(frozen=True)
class Module:
    code: str              # технический код, например "stock"
    label: str             # человекочитаемое имя для UI сборки
    is_core: bool = False  # ядро — включено у всех всегда
    url_prefix: str = ""   # префикс маршрутов, например "sklad/"
    urlconf: str = None    # dotted-путь к urls модуля, например "stock.urls"
    order: int = 100       # порядок в меню/списке сборки


# Единый реестр модулей
MODULES: dict[str, Module] = {}


def register_module(module: Module):
    MODULES[module.code] = module


# --- Ядровые модули (всегда включены) ---
# appointments приносит свои маршруты (журнал, быстрая запись) в корень.
register_module(Module("appointments", "Записи и журнал", is_core=True, order=10,
                       url_prefix="", urlconf="appointments.urls"))
register_module(Module("clients", "Клиенты", is_core=True, order=20,
                       url_prefix="", urlconf="clients.urls"))
register_module(Module("staff", "Сотрудники и график", is_core=True, order=30,
                       url_prefix="", urlconf="staff.urls"))
register_module(Module("notifications", "Уведомления", is_core=True, order=40))
register_module(Module("dashboard", "Дашборд", is_core=True, order=50))
register_module(Module("data_health", "Здоровье данных", is_core=True, order=60))

# --- Модули-тумблеры (включаются сборкой/тарифом) ---
register_module(Module("stock", "Склад и тех. карты", order=110))
register_module(Module("payroll", "Расчёт зарплат", order=120))
register_module(Module("finance", "Финансы и касса", order=130,
                       url_prefix="", urlconf="finance.urls"))
register_module(Module("subscriptions", "Абонементы и лояльность", order=140))
register_module(Module("reactivation", "Активация базы", order=150))
register_module(Module("promo", "Продвижение и акции", order=160))
register_module(Module("reviews", "Отзывы", order=170))


# Набор кодов ядровых модулей — для быстрой проверки «включён всегда»
CORE_MODULE_CODES = {m.code for m in MODULES.values() if m.is_core}


def iter_module_urlconfs():
    """Отдаёт (url_prefix, urlconf) для модулей, у которых есть импортируемый urls.py."""
    for module in sorted(MODULES.values(), key=lambda m: m.order):
        if not module.urlconf:
            continue
        try:
            import_module(module.urlconf)
        except ModuleNotFoundError:
            # Модуль заявлен в реестре, но его код ещё не написан — пропускаем.
            continue
        yield module.url_prefix, module.urlconf


def is_module_enabled(tenant, code: str) -> bool:
    """Включён ли модуль у тенанта (ядро — всегда)."""
    if code in CORE_MODULE_CODES:
        return True
    if tenant is None:
        return False
    return code in (getattr(tenant, "enabled_modules", None) or [])
