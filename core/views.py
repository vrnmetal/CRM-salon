"""
Вьюхи ядра: роутер по роли (zero-click — сразу нужный экран), заглушки дашборда
и журнала, авто-страница настроек доступа из реестра прав, тумблер подсказок.

Принцип «iPhone, а не Android»: открыл — сразу то, что нужно твоей роли, без
поиска и настройки. Сложное — за кнопкой, не в лицо.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.forms import AccountCreateForm, BrandingForm
from core.models import User
from core.permissions import REGISTRY, has_perm, requires, requires_any


# --- Домашний роутер: по роли сразу открываем нужный стартовый экран ---
@login_required
def home(request):
    user = request.user
    # Провайдерский админ — в свою панель (заглушка)
    if getattr(user, "is_provider_admin", False):
        return render(request, "core/provider_home.html")
    # Есть право на дашборд (собственник) — дашборд как главная
    if has_perm(user, "dashboard.view"):
        return redirect("dashboard")
    # Иначе — журнал записей (администратор/мастер)
    return redirect("journal")


# --- Дашборд собственника (zero-click, заглушка под будущие метрики) ---
@login_required
@requires("dashboard.view")
def dashboard(request):
    return render(request, "core/dashboard.html")


# --- Настройки доступа: UI строится АВТОМАТИЧЕСКИ из реестра прав ---
@login_required
@requires("access.manage")
def access_settings(request):
    # Группируем права по разделам для читаемого интерфейса (гранулярность — в движке,
    # простота — в UI). Отмечаем, какие есть у роли текущего пользователя.
    role = getattr(request.user, "role", None)
    current_codes = set(role.permission_codes or []) if role else set()

    sections = {}
    for perm in REGISTRY.values():
        sections.setdefault(perm.section, []).append(
            {"code": perm.code, "label": perm.label, "granted": perm.code in current_codes}
        )

    context = {
        "sections": sorted(sections.items()),
        "role_name": role.name if role else "—",
    }
    return render(request, "core/access_settings.html", context)


# ============================================================================
# Раздел «Настройки» собственника: доступы, аккаунты, брендирование
# ============================================================================

# --- Хаб настроек: карточки по доступным разделам ---
@login_required
@requires_any("access.manage", "account.manage", "branding.manage")
def settings_home(request):
    return render(request, "core/settings_home.html")


# --- Аккаунты: список сотрудников тенанта + создание ---
@login_required
@requires("account.manage")
def accounts(request):
    if request.method == "POST":
        form = AccountCreateForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            cd = form.cleaned_data
            # Создаём сотрудника в текущем тенанте с выбранной ролью
            user = User(
                username=cd["username"],
                first_name=cd["full_name"].strip(),
                tenant=request.tenant,
                role=cd["role"],
            )
            user.set_password(cd["password"])
            user.save()
            messages.success(request, f"Аккаунт {user.username} создан.")
            return redirect("accounts")
    else:
        form = AccountCreateForm(tenant=request.tenant)

    # Сотрудники тенанта (без провайдерских админов)
    staff = User.objects.filter(tenant=request.tenant, is_provider_admin=False).order_by("username")
    return render(request, "core/accounts.html", {"form": form, "staff": staff})


# --- Удаление аккаунта (нельзя удалить себя) ---
@login_required
@requires("account.manage")
@require_POST
def account_delete(request, pk):
    user = get_object_or_404(User, pk=pk, tenant=request.tenant)
    if user.id == request.user.id:
        messages.error(request, "Нельзя удалить собственный аккаунт.")
    else:
        name = user.username
        user.delete()
        messages.success(request, f"Аккаунт {name} удалён.")
    return redirect("accounts")


# --- Брендирование: имя, акцент, логотип, шрифт ---
@login_required
@requires("branding.manage")
def branding_settings(request):
    tenant = request.tenant
    if request.method == "POST":
        form = BrandingForm(request.POST, request.FILES)
        if form.is_valid():
            cd = form.cleaned_data
            tenant.brand_name = cd["brand_name"].strip()
            tenant.accent_color = cd["accent_color"].strip()
            tenant.font_preset = cd["font_preset"]
            # Логотип: удалить или заменить
            if cd["remove_logo"] and tenant.logo:
                tenant.logo.delete(save=False)
                tenant.logo = None
            if cd.get("logo"):
                tenant.logo = cd["logo"]
            tenant.save()
            messages.success(request, "Брендирование сохранено.")
            return redirect("branding_settings")
    else:
        form = BrandingForm(initial={
            "brand_name": tenant.brand_name,
            "accent_color": tenant.accent_color or "#0071E3",
            "font_preset": tenant.font_preset,
        })
    return render(request, "core/branding.html", {"form": form, "tenant": tenant})


# --- Тумблер подсказок в профиле (вкл/выкл для текущего пользователя) ---
@login_required
@require_POST
def toggle_hints(request):
    request.user.show_hints = not request.user.show_hints
    request.user.save(update_fields=["show_hints"])
    # Возвращаемся туда, откуда пришли
    return redirect(request.META.get("HTTP_REFERER", "home"))
