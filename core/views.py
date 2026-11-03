"""
Вьюхи ядра: роутер по роли (zero-click — сразу нужный экран), заглушки дашборда
и журнала, авто-страница настроек доступа из реестра прав, тумблер подсказок.

Принцип «iPhone, а не Android»: открыл — сразу то, что нужно твоей роли, без
поиска и настройки. Сложное — за кнопкой, не в лицо.
"""
import secrets as _secrets

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core import totp
from core.forms import AccountCreateForm, BrandingForm
from core.models import Role, User
from core.permissions import REGISTRY, has_perm, requires, requires_any


# ============================================================================
# Вход с двухфакторной аутентификацией (TOTP)
# ============================================================================
def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if getattr(user, "totp_enabled", False):
            # Пароль верный, но нужен второй фактор — полноценно НЕ логиним
            request.session["pre_2fa_user"] = user.id
            request.session["pre_2fa_next"] = request.GET.get("next") or ""
            return redirect("login_2fa")
        auth_login(request, user)
        return redirect(request.GET.get("next") or "home")
    return render(request, "core/login.html", {"form": form})


def login_2fa(request):
    uid = request.session.get("pre_2fa_user")
    if not uid:
        return redirect("login")
    user = User.objects.filter(pk=uid).first()
    if user is None:
        request.session.pop("pre_2fa_user", None)
        return redirect("login")

    error = None
    if request.method == "POST":
        code = (request.POST.get("code") or "").strip()
        ok = totp.verify(user.totp_secret, code)
        if not ok:
            # Пробуем как резервный код (одноразовый)
            norm = code.upper().replace(" ", "").replace("-", "")
            for h in list(user.backup_codes or []):
                if check_password(norm, h):
                    user.backup_codes.remove(h)
                    user.save(update_fields=["backup_codes"])
                    ok = True
                    break
        if ok:
            nxt = request.session.pop("pre_2fa_next", "") or "home"
            request.session.pop("pre_2fa_user", None)
            auth_login(request, user)
            return redirect(nxt)
        error = "Неверный код."
    return render(request, "core/login_2fa.html", {"error": error})


def _gen_backup_codes(n=8):
    """Генерирует n кодов вида AB12-CD34; возвращает (plain_list, hash_list)."""
    plain, hashes = [], []
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(n):
        raw = "".join(_secrets.choice(alphabet) for _ in range(8))
        plain.append(raw[:4] + "-" + raw[4:])
        hashes.append(make_password(raw))
    return plain, hashes


@login_required
def security_2fa(request):
    user = request.user
    if not getattr(user, "is_provider_admin", False):
        raise PermissionDenied("2FA доступна провайдерским аккаунтам.")

    plain_codes = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "confirm":
            if totp.verify(user.totp_secret, request.POST.get("code")):
                plain, hashes = _gen_backup_codes()
                user.totp_enabled = True
                user.backup_codes = hashes
                user.save(update_fields=["totp_enabled", "backup_codes"])
                plain_codes = plain
                messages.success(request, "2FA включена. Сохраните резервные коды.")
            else:
                messages.error(request, "Неверный код — попробуйте ещё раз.")
        elif action == "disable":
            user.totp_enabled = False
            user.totp_secret = ""
            user.backup_codes = []
            user.save(update_fields=["totp_enabled", "totp_secret", "backup_codes"])
            messages.info(request, "2FA отключена.")
            return redirect("security_2fa")
        elif action == "regen" and user.totp_enabled:
            plain, hashes = _gen_backup_codes()
            user.backup_codes = hashes
            user.save(update_fields=["backup_codes"])
            plain_codes = plain
            messages.success(request, "Резервные коды перевыпущены.")
        elif action == "reset_secret":
            user.totp_secret = ""
            user.totp_enabled = False
            user.save(update_fields=["totp_secret", "totp_enabled"])
            return redirect("security_2fa")

    # Если не включено и нет секрета — генерируем секрет для привязки
    if not user.totp_enabled and not user.totp_secret:
        user.totp_secret = totp.generate_secret()
        user.save(update_fields=["totp_secret"])

    uri = totp.provisioning_uri(user.totp_secret, user.username) if user.totp_secret else ""
    return render(request, "core/security_2fa.html", {
        "two_fa": user.totp_enabled, "secret": user.totp_secret,
        "uri": uri, "plain_codes": plain_codes,
        "backup_left": len(user.backup_codes or []),
    })


# --- Сквозной поиск: клиенты, сотрудники, услуги — с группами «где найдено» ---
@login_required
def global_search(request):
    q = (request.GET.get("q") or "").strip()
    groups = []
    if len(q) >= 2:
        # Клиенты — по имени или цифрам телефона
        if has_perm(request.user, "client.view"):
            from clients.models import Client
            items = []
            for c in Client.objects.filter(Q(full_name__icontains=q) | Q(phone__icontains=q)).order_by("full_name")[:6]:
                items.append({"name": c.full_name or c.phone, "sub": c.phone,
                              "url": reverse("client_detail", args=[c.id])})
            if items:
                groups.append({"label": "Клиенты", "items": items})

        # Сотрудники — по имени, телефону, специализации
        if has_perm(request.user, "staff.view"):
            from staff.models import Employee
            items = []
            for e in Employee.objects.filter(
                Q(full_name__icontains=q) | Q(phone__icontains=q) | Q(specialization__icontains=q)
            ).order_by("full_name")[:6]:
                sub = e.specialization or ""
                if not e.is_active:
                    sub = (sub + " · уволен").strip(" ·")
                items.append({"name": e.full_name, "sub": sub, "url": reverse("staff_list")})
            if items:
                groups.append({"label": "Сотрудники", "items": items})

        # Услуги — по названию
        if has_perm(request.user, "service.view"):
            from appointments.models import Service
            items = []
            for s in Service.objects.filter(name__icontains=q).order_by("name")[:6]:
                items.append({"name": s.name, "sub": f"{s.price:.0f} ₽ · {s.duration_min} мин",
                              "url": reverse("service_list")})
            if items:
                groups.append({"label": "Услуги", "items": items})

    return JsonResponse({"groups": groups})


# --- Домашний роутер: по роли сразу открываем нужный стартовый экран ---
@login_required
def home(request):
    user = request.user
    # Провайдерский админ (НЕ в режиме impersonation) — в свою панель
    if getattr(user, "is_provider_admin", False) and getattr(request, "impersonator", None) is None:
        return redirect("provider_home")
    # Есть право на дашборд (собственник) — дашборд как главная
    if has_perm(user, "dashboard.view"):
        return redirect("dashboard")
    # Иначе — журнал записей (администратор/мастер)
    return redirect("journal")


# --- Дашборд собственника (zero-click: метрики встречают, а не ищутся) ---
@login_required
@requires("dashboard.view")
def dashboard(request):
    from datetime import timedelta

    from django.db.models import Count, Max, Sum
    from django.utils import timezone

    from appointments.models import Appointment
    from staff.models import Employee

    A = Appointment
    now = timezone.now()
    today = timezone.localdate()
    month_start = today.replace(day=1)
    WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    # --- Выручка и чек за месяц (деньги = визиты со статусом «пришёл») ---
    came_month = A.objects.filter(status=A.STATUS_CAME, start__date__gte=month_start)
    month_came = came_month.count()
    month_revenue = int(came_month.aggregate(s=Sum("price"))["s"] or 0)
    avg_check = int(month_revenue / month_came) if month_came else 0

    # --- Повторные визиты: доля визитов за месяц от вернувшихся клиентов ---
    returning_ids = [
        r["client"] for r in A.objects.filter(status=A.STATUS_CAME)
        .values("client").annotate(n=Count("id")) if r["n"] > 1
    ]
    repeat_from = came_month.filter(client_id__in=returning_ids).count()
    repeat_rate = round(100 * repeat_from / month_came) if month_came else 0

    # --- Загрузка мастеров сегодня (занятые минуты / доступные) ---
    today_appts = A.objects.filter(start__date=today)
    booked_min = today_appts.exclude(status=A.STATUS_NOSHOW).aggregate(s=Sum("duration_min"))["s"] or 0
    masters = Employee.objects.count()
    work_min = masters * (23 - 8) * 60  # рабочее окно журнала 8–23
    load = round(100 * booked_min / work_min) if work_min else 0
    free_hours = max(0, (work_min - booked_min)) // 60

    # --- Сегодня одним взглядом ---
    today_stat = {
        "total": today_appts.count(),
        "came": today_appts.filter(status=A.STATUS_CAME).count(),
        "waiting": today_appts.filter(status__in=[A.STATUS_WAIT, A.STATUS_CONFIRMED]).count(),
        "noshow": today_appts.filter(status=A.STATUS_NOSHOW).count(),
        "revenue": int(today_appts.filter(status=A.STATUS_CAME).aggregate(s=Sum("price"))["s"] or 0),
    }

    # --- Советник: спящие клиенты (ходили, но пропали 45–120 дней) + потенциал ₽ ---
    last_visits = A.objects.filter(status=A.STATUS_CAME).values("client").annotate(last=Max("start"))
    sleeping = sum(
        1 for v in last_visits
        if v["last"] and timedelta(days=45) <= (now - v["last"]) <= timedelta(days=120)
    )
    sleeping_potential = sleeping * avg_check
    noshow_month = A.objects.filter(status=A.STATUS_NOSHOW, start__date__gte=month_start).count()

    # --- Мини-график выручки за 7 дней ---
    week = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        rev = int(A.objects.filter(status=A.STATUS_CAME, start__date=d).aggregate(s=Sum("price"))["s"] or 0)
        week.append({"label": WEEKDAYS[d.weekday()], "rev": rev, "is_today": d == today})
    max_rev = max((x["rev"] for x in week), default=0) or 1
    for x in week:
        x["pct"] = round(100 * x["rev"] / max_rev)

    context = {
        "month_revenue": month_revenue,
        "avg_check": avg_check,
        "repeat_rate": repeat_rate,
        "load": load,
        "free_hours": free_hours,
        "today_stat": today_stat,
        "sleeping": sleeping,
        "sleeping_potential": sleeping_potential,
        "noshow_month": noshow_month,
        "week": week,
    }
    return render(request, "core/dashboard.html", context)


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


# --- История действий (с отменой) ---
@login_required
@requires("history.view")
def history(request):
    from core.activity import human_model
    from core.models import ActivityLog

    entries = ActivityLog.objects.select_related("actor", "undone_by")[:200]
    rows = []
    for e in entries:
        rows.append({"e": e, "model": human_model(e.model_label)})
    return render(request, "core/history.html", {
        "rows": rows, "can_undo": has_perm(request.user, "history.undo"),
    })


@login_required
@requires("history.undo")
@require_POST
def history_undo(request, pk):
    from core.activity import undo
    from core.models import ActivityLog

    entry = get_object_or_404(ActivityLog, pk=pk)
    ok, msg = undo(entry, request.user)
    (messages.success if ok else messages.error)(request, msg)
    return redirect("history")


# --- Тумблер подсказок в профиле (вкл/выкл для текущего пользователя) ---
@login_required
@require_POST
def toggle_hints(request):
    request.user.show_hints = not request.user.show_hints
    request.user.save(update_fields=["show_hints"])
    # Возвращаемся туда, откуда пришли
    return redirect(request.META.get("HTTP_REFERER", "home"))
