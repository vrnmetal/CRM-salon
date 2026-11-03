"""
Приём оплаты по записи. Создаёт Payment и отдаёт его драйверу (терминал).
Подтверждение/отмена — отдельными действиями (в проде подтверждение прилетит
вебхуком от терминала; здесь — кнопкой-эмуляцией).
"""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from appointments.models import Appointment
from core.models import AuditLog
from core.permissions import requires
from payments.drivers import DEFAULT_DRIVER, get_driver
from payments.models import Payment


def _back(appt_id):
    return redirect(reverse("appointment_detail", args=[appt_id]))


def _audit(request, payment, action):
    AuditLog.objects.create(
        tenant=getattr(request, "tenant", None), user=request.user,
        action=action, target=f"appt#{payment.appointment_id}",
        meta={"amount": str(payment.amount), "provider": payment.provider, "payment": payment.id},
    )


# --- Принять оплату: создать платёж и отправить на терминал ---
@login_required
@requires("payment.charge")
@require_POST
def payment_charge(request, appt_pk):
    from decimal import Decimal
    appt = get_object_or_404(Appointment, pk=appt_pk)

    if appt.payments.filter(status=Payment.PAID).exists():
        messages.info(request, "Запись уже оплачена.")
        return _back(appt_pk)
    if appt.payments.filter(status=Payment.SENT).exists():
        messages.info(request, "Оплата уже отправлена на терминал и ждёт подтверждения.")
        return _back(appt_pk)

    method = request.POST.get("method", "card")  # card / cash

    # Наличные — оплачено сразу, без терминала и комиссии
    if method == "cash":
        pay = Payment.objects.create(
            appointment=appt, amount=appt.price or 0, method=Payment.METHOD_CASH,
            provider="cash", status=Payment.PAID,
        )
        _audit(request, pay, "payment.cash")
        messages.success(request, "Оплачено наличными.")
        return _back(appt_pk)

    # Карта — через терминал, с комиссией эквайринга (себестоимость продажи)
    acq = getattr(request.tenant, "acquiring_pct", 0) or Decimal("0")
    fee = (appt.price or 0) * acq / Decimal("100")
    driver = get_driver(DEFAULT_DRIVER)
    pay = Payment.objects.create(
        appointment=appt, amount=appt.price or 0, method=Payment.METHOD_TERMINAL,
        provider=driver.code, status=Payment.PENDING, acquiring_fee=fee,
    )
    try:
        res = driver.charge(pay)
        pay.status = res.status
        pay.external_id = res.external_id
        pay.error = "" if res.ok else res.message
        messages.success(request, res.message or "Отправлено на терминал.")
    except NotImplementedError as exc:
        pay.status = Payment.FAILED
        pay.error = str(exc)
        messages.error(request, str(exc))
    pay.save()
    _audit(request, pay, "payment.charge")
    return _back(appt_pk)


# --- Настройки эквайринга (владелец) ---
@login_required
@requires("branding.manage")
def payment_settings(request):
    from decimal import Decimal, InvalidOperation
    tenant = request.tenant
    if request.method == "POST":
        raw = (request.POST.get("acquiring_pct") or "0").replace(",", ".")
        try:
            tenant.acquiring_pct = Decimal(raw)
        except (InvalidOperation, TypeError):
            tenant.acquiring_pct = Decimal("0")
        tenant.save(update_fields=["acquiring_pct"])
        messages.success(request, "Настройки оплаты сохранены.")
        return redirect("payment_settings")
    return render(request, "payments/settings.html", {"tenant": tenant})


# --- Подтверждение оплаты (в проде — вебхук терминала; тут кнопка-эмуляция) ---
@login_required
@requires("payment.charge")
@require_POST
def payment_confirm(request, pk):
    pay = get_object_or_404(Payment, pk=pk)
    if pay.status == Payment.SENT:
        pay.status = Payment.PAID
        pay.save(update_fields=["status", "updated_at"])
        _audit(request, pay, "payment.paid")
        messages.success(request, "Оплата подтверждена.")
    return _back(pay.appointment_id)


# --- Отмена платежа (пока не завершён) ---
@login_required
@requires("payment.charge")
@require_POST
def payment_cancel(request, pk):
    pay = get_object_or_404(Payment, pk=pk)
    if pay.is_open:
        pay.status = Payment.CANCELED
        pay.save(update_fields=["status", "updated_at"])
        _audit(request, pay, "payment.cancel")
        messages.info(request, "Платёж отменён.")
    return _back(pay.appointment_id)
