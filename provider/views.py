"""
Провайдерская панель — control plane над всеми тенантами.

Принцип: управляем тенантами (статус, тариф, модули, домен, оплата), но НЕ лезем
в клиентские базы напрямую (152-ФЗ). Единственный вход «внутрь» салона —
impersonation с обязательной записью в неизменяемый AuditLog.

Доступ: только is_provider_admin (права provider.* в has_perm автоматически
выдаются провайдерскому админу).
"""
import secrets
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import AuditLog, Tenant, User
from core.modules import MODULES
from core.permissions import requires


def _non_core_modules():
    return [m for m in sorted(MODULES.values(), key=lambda x: x.order) if not m.is_core]


def _owner_of(tenant):
    """Владелец салона для impersonation: аккаунт с правом доступа, иначе первый."""
    users = list(User.objects.filter(tenant=tenant, is_provider_admin=False))
    for u in users:
        if "access.manage" in (u.permission_codes or []):
            return u
    return users[0] if users else None


def _log(request, tenant, action, target="", **meta):
    actor = getattr(request, "impersonator", None) or request.user
    AuditLog.objects.create(tenant=tenant, user=actor, action=action, target=target, meta=meta)


# --- Главная: метрики парка + список тенантов ---
@login_required
@requires("provider.tenants.view")
def home(request):
    today = timezone.localdate()
    tenants = list(Tenant.objects.annotate(accounts=Count("users")).order_by("-created_at"))

    # Последняя активность по тенанту (последняя созданная запись) — unscoped-менеджер
    from appointments.models import Appointment
    last_dt = {}
    for a in Appointment.all_objects.order_by("tenant_id", "-created_at").values("tenant_id", "created_at"):
        last_dt.setdefault(a["tenant_id"], a["created_at"])

    rows = []
    overdue = 0
    for t in tenants:
        is_overdue = bool(t.paid_until and t.paid_until < today)
        if is_overdue:
            overdue += 1
        rows.append({
            "t": t,
            "accounts": t.accounts,
            "modules_on": len([c for c in (t.enabled_modules or [])]),
            "last": last_dt.get(t.id),
            "overdue": is_overdue,
        })

    kpis = {
        "total": len(tenants),
        "active": sum(1 for t in tenants if t.is_active),
        "frozen": sum(1 for t in tenants if not t.is_active),
        "overdue": overdue,
    }
    return render(request, "provider/home.html", {"rows": rows, "kpis": kpis, "today": today})


# --- Карточка тенанта: управление ---
@login_required
@requires("provider.tenants.view")
def tenant_detail(request, pk):
    t = get_object_or_404(Tenant, pk=pk)
    modules = [{"m": m, "on": m.code in (t.enabled_modules or [])} for m in _non_core_modules()]
    accounts = User.objects.filter(tenant=t, is_provider_admin=False).order_by("username")
    audit = AuditLog.objects.filter(tenant=t).order_by("-created_at")[:20]
    return render(request, "provider/tenant.html", {
        "t": t, "modules": modules, "accounts": accounts, "audit": audit,
        "base_domain": _base_domain(),
    })


def _base_domain():
    from django.conf import settings
    return getattr(settings, "BASE_DOMAIN", "example.com")


# --- Рубильник доступа (заморозка неплатящего, данные не трогаем) ---
@login_required
@requires("provider.tenant.toggle")
@require_POST
def tenant_toggle(request, pk):
    t = get_object_or_404(Tenant, pk=pk)
    t.is_active = not t.is_active
    t.save(update_fields=["is_active"])
    _log(request, t, "tenant.toggle", target=t.slug, active=t.is_active)
    messages.success(request, f"Салон «{t.name}» {'включён' if t.is_active else 'заморожен'}.")
    return redirect("provider_tenant", pk=pk)


# --- Модули-тумблеры (ручная продажа апгрейда) ---
@login_required
@requires("provider.tenant.manage")
@require_POST
def tenant_modules(request, pk):
    t = get_object_or_404(Tenant, pk=pk)
    allowed = {m.code for m in _non_core_modules()}
    chosen = sorted(set(request.POST.getlist("modules")) & allowed)
    t.enabled_modules = chosen
    t.save(update_fields=["enabled_modules"])
    _log(request, t, "tenant.modules", target=t.slug, modules=chosen)
    messages.success(request, "Набор модулей сохранён.")
    return redirect("provider_tenant", pk=pk)


# --- Тариф + оплата (ручная отметка) ---
@login_required
@requires("provider.tenant.manage")
@require_POST
def tenant_billing(request, pk):
    t = get_object_or_404(Tenant, pk=pk)
    t.plan = (request.POST.get("plan") or "").strip()
    raw = request.POST.get("paid_until")
    if raw:
        try:
            t.paid_until = date.fromisoformat(raw)
        except ValueError:
            pass
    else:
        t.paid_until = None
    t.save(update_fields=["plan", "paid_until"])
    _log(request, t, "tenant.billing", target=t.slug, plan=t.plan,
         paid_until=t.paid_until.isoformat() if t.paid_until else None)
    messages.success(request, "Тариф и оплата сохранены.")
    return redirect("provider_tenant", pk=pk)


# --- Кастомный домен: задать (сбрасывает подтверждение, выдаёт токен) ---
@login_required
@requires("provider.tenant.manage")
@require_POST
def tenant_domain(request, pk):
    t = get_object_or_404(Tenant, pk=pk)
    domain = (request.POST.get("custom_domain") or "").strip().lower()
    for pfx in ("https://", "http://"):
        if domain.startswith(pfx):
            domain = domain[len(pfx):]
    domain = domain.strip("/").split("/")[0]
    if domain != (t.custom_domain or ""):
        t.custom_domain = domain or None
        t.custom_domain_verified = False
        t.domain_token = secrets.token_hex(16) if domain else ""
        t.save(update_fields=["custom_domain", "custom_domain_verified", "domain_token"])
        _log(request, t, "tenant.domain.set", target=domain)
        messages.success(request, "Домен сохранён. Подтвердите владение по инструкции.")
    return redirect("provider_tenant", pk=pk)


# --- Подтверждение домена: авто (DNS TXT) или вручную провайдером ---
@login_required
@requires("provider.tenant.manage")
@require_POST
def tenant_domain_verify(request, pk):
    t = get_object_or_404(Tenant, pk=pk)
    if not t.custom_domain:
        messages.error(request, "Домен не задан.")
        return redirect("provider_tenant", pk=pk)

    # Ручное подтверждение (провайдер сам проверил DNS)
    if request.POST.get("manual"):
        t.custom_domain_verified = True
        t.save(update_fields=["custom_domain_verified"])
        _log(request, t, "tenant.domain.verify", target=t.custom_domain, mode="manual")
        messages.success(request, "Домен подтверждён вручную.")
        return redirect("provider_tenant", pk=pk)

    # Авто-проверка TXT-записи _salon-verify.<domain> = токен (если доступен dnspython)
    ok = False
    try:
        import dns.resolver  # type: ignore
        answers = dns.resolver.resolve(f"_salon-verify.{t.custom_domain}", "TXT")
        for rdata in answers:
            if t.domain_token in str(rdata).strip('"'):
                ok = True
                break
    except Exception:
        ok = False

    if ok:
        t.custom_domain_verified = True
        t.save(update_fields=["custom_domain_verified"])
        _log(request, t, "tenant.domain.verify", target=t.custom_domain, mode="auto")
        messages.success(request, "Домен подтверждён.")
    else:
        messages.error(request, "TXT-запись не найдена. Проверьте DNS или подтвердите вручную.")
    return redirect("provider_tenant", pk=pk)


# --- Создание тенанта (онбординг салона + первый владелец) ---
@login_required
@requires("provider.tenant.manage")
def tenant_create(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        slug = (request.POST.get("slug") or "").strip().lower()
        owner_login = (request.POST.get("owner_login") or "").strip()
        owner_pass = request.POST.get("owner_pass") or ""
        chosen = sorted(set(request.POST.getlist("modules")) & {m.code for m in _non_core_modules()})

        if not (name and slug and owner_login and owner_pass):
            messages.error(request, "Заполните название, поддомен, логин и пароль владельца.")
        elif Tenant.objects.filter(slug=slug).exists():
            messages.error(request, f"Поддомен «{slug}» уже занят.")
        elif User.objects.filter(username=owner_login).exists():
            messages.error(request, f"Логин «{owner_login}» уже занят.")
        else:
            t = Tenant.objects.create(name=name, slug=slug, brand_name=name,
                                      is_active=True, enabled_modules=chosen)
            # Роль-пресет «Собственник» + аккаунт владельца с полными правами
            from core.models import Role
            from core.permissions import role_presets
            preset = role_presets()["owner"]
            role = Role.objects.create(tenant=t, name=preset["name"],
                                       preset_code="owner", permission_codes=preset["codes"])
            owner = User(username=owner_login, tenant=t, role=role,
                         permission_codes=list(preset["codes"]))
            owner.set_password(owner_pass)
            owner.save()
            _log(request, t, "tenant.create", target=slug)
            messages.success(request, f"Салон «{name}» создан. Владелец: {owner_login}.")
            return redirect("provider_tenant", pk=t.id)

    return render(request, "provider/tenant_create.html", {"modules": _non_core_modules()})


# --- Impersonation: войти как владелец салона (с аудитом) ---
@login_required
@requires("provider.impersonate")
@require_POST
def impersonate_start(request, pk):
    t = get_object_or_404(Tenant, pk=pk)
    owner = _owner_of(t)
    if owner is None:
        messages.error(request, "У салона нет аккаунтов для входа.")
        return redirect("provider_tenant", pk=pk)
    request.session["impersonate_user_id"] = owner.id
    _log(request, t, "impersonate.start", target=owner.username)
    messages.info(request, f"Вы вошли как салон «{t.name}».")
    return redirect("home")


# --- Выход из impersonation (доступен, пока провайдер «внутри» салона) ---
@login_required
@require_POST
def impersonate_stop(request):
    imp = getattr(request, "impersonator", None)
    if imp is None:
        return redirect("home")
    tenant = getattr(request.user, "tenant", None)
    _log(request, tenant, "impersonate.stop", target=getattr(request.user, "username", ""))
    request.session.pop("impersonate_user_id", None)
    messages.success(request, "Вы вышли из режима салона.")
    return redirect("provider_home")


# --- Сброс пароля аккаунта салона (владелец забыл — провайдер восстанавливает) ---
@login_required
@requires("provider.tenant.manage")
@require_POST
def account_reset(request, pk):
    u = get_object_or_404(User, pk=pk, is_provider_admin=False)
    newp = (request.POST.get("password") or "").strip()
    if not newp:
        newp = secrets.token_urlsafe(9)  # авто-генерация, если не задали вручную
    u.set_password(newp)
    u.save()
    _log(request, u.tenant, "account.reset_password", target=u.username)
    messages.success(request, f"Пароль для «{u.username}» сброшен. Новый пароль: {newp}")
    return redirect("provider_tenant", pk=u.tenant_id)


# --- Смена логина аккаунта салона ---
@login_required
@requires("provider.tenant.manage")
@require_POST
def account_rename(request, pk):
    u = get_object_or_404(User, pk=pk, is_provider_admin=False)
    new = (request.POST.get("username") or "").strip()
    if not new:
        messages.error(request, "Логин не может быть пустым.")
    elif User.objects.filter(username=new).exclude(pk=u.pk).exists():
        messages.error(request, f"Логин «{new}» уже занят.")
    else:
        old = u.username
        u.username = new
        u.save(update_fields=["username"])
        _log(request, u.tenant, "account.rename", target=f"{old} → {new}")
        messages.success(request, f"Логин изменён: {old} → {new}.")
    return redirect("provider_tenant", pk=u.tenant_id)


# --- Неизменяемый журнал действий провайдера ---
@login_required
@requires("provider.tenants.view")
def audit_log(request):
    entries = (AuditLog.objects.select_related("tenant", "user")
               .order_by("-created_at")[:200])
    return render(request, "provider/audit.html", {"entries": entries})
