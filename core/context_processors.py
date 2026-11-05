"""
Контекст-процессоры: брендирование, UI-флаги и управляемое меню сайдбара.

Пункты основного меню определены ЗДЕСЬ единым списком (ключ, право, маршрут,
иконка), а не разбросаны по шаблону — так их можно сортировать перетаскиванием
(персональный порядок хранится в User.sidebar_order).
"""
from django.urls import NoReverseMatch, reverse
from django.utils.safestring import mark_safe

from core.branding import font_stack
from core.tenancy import get_current_tenant

_S = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" width="18" height="18"'

# key, permission, url_name, label, active_url_names, svg
_NAV_SPEC = [
    ("dashboard", "dashboard.view", "dashboard", "Дашборд",
     ("dashboard", "dash_records", "dash_finance"),
     f'<svg {_S}><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>'),
    ("journal", "appointment.view", "journal", "Журнал",
     ("journal",),
     f'<svg {_S}><rect x="3" y="4" width="18" height="17" rx="2.5"/><path d="M3 9h18M8 2.5v3M16 2.5v3"/></svg>'),
    ("notifications", "notification.view", "notifications_panel", "Напоминания",
     ("notifications_panel", "notification_telegram", "notification_sms"),
     f'<svg {_S}><path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6M10 20a2 2 0 0 0 4 0"/></svg>'),
    ("clients", "client.view", "client_list", "Клиенты",
     ("client_list", "client_detail"),
     f'<svg {_S}><circle cx="9" cy="8" r="3.2"/><path d="M3.5 20a5.5 5.5 0 0 1 11 0M16 5.5a3 3 0 0 1 0 5.5M17.5 20a5 5 0 0 0-3-4.6"/></svg>'),
    ("staff", "staff.view", "staff_list", "Сотрудники",
     ("staff_list",),
     f'<svg {_S}><circle cx="12" cy="8" r="3.4"/><path d="M5 20a7 7 0 0 1 14 0"/></svg>'),
    ("services", "service.view", "service_list", "Услуги",
     ("service_list",),
     f'<svg {_S}><path d="M4 7h16M4 12h16M4 17h10"/></svg>'),
    ("finance", "finance.view", "finance_home", "Финансы",
     ("finance_home",),
     f'<svg {_S}><path d="M3 7h18v12H3zM3 11h18M7 15h4"/></svg>'),
    ("payroll", "payroll.view", "payroll_home", "Зарплаты",
     ("payroll_home",),
     f'<svg {_S}><circle cx="12" cy="12" r="9"/><path d="M12 7v10M9.5 9.5a2.5 2 0 0 1 5 0c0 2-5 1-5 3a2.5 2 0 0 0 5 0"/></svg>'),
    ("stock", "stock.view", "stock_home", "Склад",
     ("stock_home", "techcards", "service_card"),
     f'<svg {_S}><path d="M3 7l9-4 9 4-9 4-9-4zM3 7v10l9 4 9-4V7M12 11v10"/></svg>'),
    ("subscriptions", "subscription.view", "subs_plans", "Абонементы",
     ("subs_plans", "subs_sell"),
     f'<svg {_S}><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M2 10h20M6 14h4"/></svg>'),
]
_DEFAULT_INDEX = {spec[0]: i for i, spec in enumerate(_NAV_SPEC)}


def branding(request):
    tenant = get_current_tenant()
    if tenant is None:
        return {"brand": {"name": "", "logo_url": "", "accent": "", "font": ""}}
    return {
        "brand": {
            "name": tenant.brand_name or tenant.name,
            "logo_url": tenant.logo.url if tenant.logo else "",
            "accent": tenant.accent_color or "",
            "font": font_stack(tenant.font_preset),
        }
    }


def ui_flags(request):
    user = getattr(request, "user", None)
    authed = getattr(user, "is_authenticated", False)
    show_hints = bool(getattr(user, "show_hints", False)) if authed else False
    return {"show_hints": show_hints}


def sidebar_nav(request):
    """Пункты основного меню в персональном порядке пользователя (для сортировки)."""
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return {"sidebar_items": []}

    from core.permissions import has_perm

    name = request.resolver_match.url_name if getattr(request, "resolver_match", None) else ""
    items = []
    for key, perm, url_name, label, actives, svg in _NAV_SPEC:
        if not has_perm(user, perm):
            continue
        try:
            url = reverse(url_name)
        except NoReverseMatch:
            continue
        active = name in actives or (key == "payroll" and name and "payroll" in name)
        item = {"key": key, "url": url, "label": label, "icon": mark_safe(svg),
                "active": active, "badge": 0}
        if key == "notifications":
            try:
                from notifications.service import due_appointments
                item["badge"] = due_appointments().count()
            except Exception:
                item["badge"] = 0
        items.append(item)

    # Персональный порядок: сначала сохранённые ключи в их порядке, затем остальные
    order = list(getattr(user, "sidebar_order", None) or [])
    pos = {k: i for i, k in enumerate(order)}
    items.sort(key=lambda it: pos.get(it["key"], 1000 + _DEFAULT_INDEX.get(it["key"], 0)))

    # Отметка скрытых (персонально): в меню их не показываем, в панели настройки — показываем
    hidden = set(getattr(user, "sidebar_hidden", None) or [])
    for it in items:
        it["hidden"] = it["key"] in hidden

    return {
        "sidebar_items": [it for it in items if not it["hidden"]],  # видимое меню
        "sidebar_menu": items,                                      # всё — для панели настройки
    }
