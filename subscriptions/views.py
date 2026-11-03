"""Абонементы/сертификаты: продукты салона, продажа клиенту, списание при оплате."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from appointments.models import Appointment, Service
from clients.models import Client
from core.models import AuditLog
from core.permissions import requires
from payments.models import Payment
from subscriptions.models import ClientSubscription, SubscriptionPlan, SubscriptionUsage


def _dec(raw, default="0"):
    try:
        return Decimal(str(raw).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _int(raw, default=0):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


# --- Продукты салона (что продаём) ---
@login_required
@requires("subscription.view")
def plans_home(request):
    plans = SubscriptionPlan.objects.all()
    services = Service.objects.filter(is_active=True)
    return render(request, "subscriptions/plans.html", {"plans": plans, "services": services})


@login_required
@requires("subscription.manage")
@require_POST
def plan_create(request):
    name = (request.POST.get("name") or "").strip()
    if name:
        kind = request.POST.get("kind") or SubscriptionPlan.VISITS
        SubscriptionPlan.objects.create(
            name=name, kind=kind,
            service_id=request.POST.get("service") or None,
            total_uses=_int(request.POST.get("total_uses")),
            price=_dec(request.POST.get("price")),
            value=_dec(request.POST.get("value")),
            validity_days=_int(request.POST.get("validity_days")),
        )
        messages.success(request, f"Продукт «{name}» создан.")
    return redirect("subs_plans")


@login_required
@requires("subscription.manage")
@require_POST
def plan_toggle(request, pk):
    p = get_object_or_404(SubscriptionPlan, pk=pk)
    p.is_active = not p.is_active
    p.save(update_fields=["is_active"])
    return redirect("subs_plans")


# --- Продажа абонемента клиенту ---
@login_required
@requires("subscription.sell")
def sell(request, client_pk):
    client = get_object_or_404(Client, pk=client_pk)
    if request.method == "POST":
        plan = SubscriptionPlan.objects.filter(pk=request.POST.get("plan"), is_active=True).first()
        if plan:
            today = timezone.localdate()
            expires = today + timedelta(days=plan.validity_days) if plan.validity_days else None
            is_visits = plan.kind == SubscriptionPlan.VISITS
            ClientSubscription.objects.create(
                client=client, plan=plan, name=plan.name, kind=plan.kind, service=plan.service,
                remaining_uses=plan.total_uses if is_visits else 0,
                balance=plan.value if not is_visits else 0,
                expires_at=expires,
            )
            AuditLog.objects.create(tenant=request.tenant, user=request.user,
                                    action="subscription.sell", target=f"client#{client.id}",
                                    meta={"plan": plan.name, "price": str(plan.price)})
            messages.success(request, f"Абонемент «{plan.name}» продан клиенту {client.full_name}.")
            return redirect("client_detail", pk=client.id)

    plans = SubscriptionPlan.objects.filter(is_active=True)
    return render(request, "subscriptions/sell.html", {"client": client, "plans": plans})


# --- Списание абонементом при оплате записи ---
@login_required
@requires("subscription.redeem")
@require_POST
def redeem(request, pk):
    sub = get_object_or_404(ClientSubscription, pk=pk)
    appt = get_object_or_404(Appointment, pk=request.POST.get("appointment"))
    today = timezone.localdate()

    if not sub.is_valid(today) or not sub.covers(appt):
        messages.error(request, "Этот абонемент не подходит для оплаты визита.")
        return redirect(reverse("appointment_detail", args=[appt.id]))
    if appt.payments.filter(status=Payment.PAID).exists():
        messages.info(request, "Запись уже оплачена.")
        return redirect(reverse("appointment_detail", args=[appt.id]))

    uses_spent = 0
    amount_spent = Decimal("0")
    if sub.kind == SubscriptionPlan.VISITS:
        sub.remaining_uses -= 1
        uses_spent = 1
        amount_spent = appt.price or 0
        if sub.remaining_uses <= 0:
            sub.status = ClientSubscription.FINISHED
    else:
        sub.balance -= (appt.price or 0)
        amount_spent = appt.price or 0
        if sub.balance <= 0:
            sub.status = ClientSubscription.FINISHED
    sub.save()

    SubscriptionUsage.objects.create(subscription=sub, appointment=appt,
                                     uses_spent=uses_spent, amount_spent=amount_spent)
    Payment.objects.create(
        appointment=appt, amount=appt.price or 0, method=Payment.METHOD_SUBSCRIPTION,
        provider="subscription", status=Payment.PAID, external_id=f"sub#{sub.id}",
    )
    messages.success(request, "Оплачено абонементом.")
    return redirect(reverse("appointment_detail", args=[appt.id]))
