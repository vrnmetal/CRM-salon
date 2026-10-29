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
from core.models import Role, User
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


# --- Настройки доступа: РЕДАКТИРУЕМЫЕ галочки прав по ролям ---
# UI строится из реестра прав; собственник отмечает, что можно делать каждой роли.
@login_required
@requires("access.manage")
def access_settings(request):
    from django.urls import reverse

    roles = list(Role.objects.filter(tenant=request.tenant).order_by("name"))

    # Какую роль редактируем: из параметра, иначе роль текущего пользователя, иначе первая
    rid = request.POST.get("role") if request.method == "POST" else request.GET.get("role")
    role = next((r for r in roles if str(r.id) == str(rid)), None)
    if role is None:
        role = request.user.role if request.user.role in roles else (roles[0] if roles else None)

    # Провайдерские права не редактируются на уровне тенанта
    editable = {code: p for code, p in REGISTRY.items() if p.module != "provider"}

    if request.method == "POST" and role is not None:
        checked = set(request.POST.getlist("perms")) & set(editable.keys())
        # Защита: нельзя снять «Настраивать доступы» со СВОЕЙ роли (иначе самоблок)
        if role.id == getattr(request.user.role, "id", None):
            checked.add("access.manage")
        role.permission_codes = sorted(checked)
        role.save(update_fields=["permission_codes"])
        messages.success(request, f"Права роли «{role.name}» сохранены.")
        return redirect(reverse("access_settings") + f"?role={role.id}")

    current = set(role.permission_codes or []) if role else set()
    sections = {}
    for p in editable.values():
        sections.setdefault(p.section, []).append(
            {"code": p.code, "label": p.label, "granted": p.code in current}
        )

    context = {
        "roles": roles,
        "role": role,
        "sections": sorted(sections.items()),
        # Своя роль — предупредим, что access.manage заблокирован к снятию
        "is_own_role": role is not None and role.id == getattr(request.user.role, "id", None),
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
            role = cd["role"]
            # Создаём сотрудника; права КОПИРУЕМ из пресета роли на сам аккаунт
            user = User(
                username=cd["username"],
                first_name=cd["full_name"].strip(),
                tenant=request.tenant,
                role=role,
                permission_codes=list(role.permission_codes or []),
            )
            user.set_password(cd["password"])
            user.save()
            messages.success(request, f"Аккаунт {user.username} создан.")
            return redirect("accounts")
    else:
        form = AccountCreateForm(tenant=request.tenant)

    # Сотрудники тенанта (без провайдерских админов) + роли-пресеты
    staff = User.objects.filter(tenant=request.tenant, is_provider_admin=False).order_by("username")
    roles = Role.objects.filter(tenant=request.tenant).order_by("name")
    return render(request, "core/accounts.html", {"form": form, "staff": staff, "roles": roles})


# --- Применить пресет роли к аккаунту (копирует галочки роли в права аккаунта) ---
@login_required
@requires("account.manage")
@require_POST
def account_apply_preset(request, pk):
    user = get_object_or_404(User, pk=pk, tenant=request.tenant)
    role = Role.objects.filter(tenant=request.tenant, pk=request.POST.get("role")).first()
    if role is None:
        messages.error(request, "Роль не найдена.")
        return redirect("accounts")
    user.role = role
    user.permission_codes = list(role.permission_codes or [])
    # Защита: нельзя лишить себя доступа к настройкам
    if user.id == request.user.id and "access.manage" not in user.permission_codes:
        user.permission_codes.append("access.manage")
    user.save(update_fields=["role", "permission_codes"])
    messages.success(request, f"Пресет «{role.name}» применён к {user.username}.")
    return redirect("accounts")


# --- Персональная настройка доступа КОНКРЕТНОГО аккаунта (галочки прав) ---
@login_required
@requires("account.manage")
def account_access(request, pk):
    user = get_object_or_404(User, pk=pk, tenant=request.tenant)
    # Провайдерские права не редактируются на уровне тенанта
    editable = {code: p for code, p in REGISTRY.items() if p.module != "provider"}

    if request.method == "POST":
        checked = set(request.POST.getlist("perms")) & set(editable.keys())
        # Нельзя снять «Настраивать доступы» с самого себя
        if user.id == request.user.id:
            checked.add("access.manage")
        user.permission_codes = sorted(checked)
        user.save(update_fields=["permission_codes"])
        messages.success(request, f"Доступ аккаунта {user.username} сохранён.")
        return redirect("accounts")

    current = set(user.permission_codes or [])
    sections = {}
    for p in editable.values():
        sections.setdefault(p.section, []).append(
            {"code": p.code, "label": p.label, "granted": p.code in current}
        )
    context = {
        "account": user,
        "sections": sorted(sections.items()),
        "is_self": user.id == request.user.id,
        "roles": Role.objects.filter(tenant=request.tenant).order_by("name"),
    }
    return render(request, "core/account_access.html", context)


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
