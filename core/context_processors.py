"""
Контекст-процессоры: отдают в шаблоны брендирование тенанта и UI-флаги.
"""
from core.branding import font_stack
from core.tenancy import get_current_tenant


# --- Брендирование: имя бренда, лого, акцентный цвет, шрифт текущего тенанта ---
def branding(request):
    tenant = get_current_tenant()
    if tenant is None:
        return {"brand": {"name": "", "logo_url": "", "accent": "", "font": ""}}
    return {
        "brand": {
            "name": tenant.brand_name or tenant.name,
            "logo_url": tenant.logo.url if tenant.logo else "",
            # Акцент тенанта подменит --accent в base.html (white-label)
            "accent": tenant.accent_color or "",
            # Шрифт-пресет подменит --font-sans (если выбран)
            "font": font_stack(tenant.font_preset),
        }
    }


# --- UI-флаги: показывать ли подсказки (из профиля пользователя) ---
def ui_flags(request):
    user = getattr(request, "user", None)
    show_hints = bool(getattr(user, "show_hints", False)) if getattr(user, "is_authenticated", False) else False
    return {"show_hints": show_hints}
