"""
Раздел «Напоминания» — одна точка в сайдбаре, внутри вкладки:
  • Обзор (panel)     — кому пора напомнить, общий журнал, общие настройки;
  • Telegram          — токен/статус бота, подписка, журнал канала;
  • SMS               — агрегатор/логин/имя отправителя, журнал канала.
Плюс публичный вебхук Telegram.
"""
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt

from appointments.models import Appointment
from core.models import Tenant
from core.permissions import has_perm, requires
from core.tenancy import tenant_context
from notifications import telegram as tg
from notifications.models import Notification, NotificationSettings
from notifications.service import due_appointments, get_settings, send_reminder


def _common(request):
    return {
        "settings": get_settings(),
        "can_send": has_perm(request.user, "notification.send"),
        "can_manage": has_perm(request.user, "notification.manage"),
    }


def _require_manage(request):
    if not has_perm(request.user, "notification.manage"):
        raise PermissionDenied("Нет права: notification.manage")


# --- Обзор: кому пора + журнал + общие настройки ---
@login_required
@requires("notification.view")
def panel(request):
    s = get_settings()
    if request.method == "POST":
        _require_manage(request)
        s.auto_enabled = bool(request.POST.get("auto_enabled"))
        try:
            s.hours_before = max(1, min(720, int(request.POST.get("hours_before") or 24)))
        except (ValueError, TypeError):
            s.hours_before = 24
        channel = request.POST.get("channel") or NotificationSettings.CH_CONSOLE
        valid = {c for c, _ in NotificationSettings.CHANNEL_CHOICES}
        s.channel = channel if channel in valid else NotificationSettings.CH_CONSOLE
        s.template = (request.POST.get("template") or "").strip() or s.template
        s.save()
        messages.success(request, "Настройки сохранены.")
        return redirect("notifications_panel")

    ctx = _common(request)
    ctx.update({
        "active": "overview",
        "due": list(due_appointments()),
        "log": list(Notification.objects.select_related("appointment", "appointment__client", "created_by")[:50]),
        "channels": NotificationSettings.CHANNEL_CHOICES,
    })
    return render(request, "notifications/panel.html", ctx)


# --- Вкладка Telegram ---
@login_required
@requires("notification.view")
def channel_telegram(request):
    s = get_settings()
    if request.method == "POST":
        _require_manage(request)
        s.telegram_bot_token = (request.POST.get("telegram_bot_token") or "").strip()
        s.save(update_fields=["telegram_bot_token"])
        messages.success(request, "Токен бота сохранён.")
        return redirect("notification_telegram")

    bot, bot_link = None, ""
    if s.telegram_bot_token:
        me = tg.get_me(s.telegram_bot_token)
        if me.get("ok"):
            username = (me.get("result") or {}).get("username", "")
            bot = {"username": username, "name": (me.get("result") or {}).get("first_name", "")}
            bot_link = f"https://t.me/{username}" if username else ""
        else:
            bot = {"error": me.get("description", "бот недоступен")}
    ctx = _common(request)
    ctx.update({
        "active": "telegram",
        "bot": bot,
        "bot_link": bot_link,
        "webhook_url": request.build_absolute_uri(f"/tg/{request.tenant.slug}/") if request.tenant else "",
        "log": list(Notification.objects.filter(channel="telegram").select_related("appointment__client")[:50]),
    })
    return render(request, "notifications/telegram.html", ctx)


# --- Вкладка SMS ---
@login_required
@requires("notification.view")
def channel_sms(request):
    s = get_settings()
    if request.method == "POST":
        _require_manage(request)
        s.sms_provider = (request.POST.get("sms_provider") or "smsc").strip()
        s.sms_login = (request.POST.get("sms_login") or "").strip()
        s.sms_password = (request.POST.get("sms_password") or "").strip()
        s.sms_sender = (request.POST.get("sms_sender") or "").strip()
        s.save(update_fields=["sms_provider", "sms_login", "sms_password", "sms_sender"])
        messages.success(request, "Настройки SMS сохранены.")
        return redirect("notification_sms")

    ctx = _common(request)
    ctx.update({
        "active": "sms",
        "log": list(Notification.objects.filter(channel="sms").select_related("appointment__client")[:50]),
    })
    return render(request, "notifications/sms.html", ctx)


# --- Ручная отправка напоминания по записи ---
@login_required
@requires("notification.send")
def send(request, appt_id):
    if request.method != "POST":
        return redirect("notifications_panel")
    appt = get_object_or_404(Appointment, pk=appt_id)
    notif = send_reminder(appt, by_user=request.user)
    if notif.status == Notification.ST_SENT:
        messages.success(request, "Напоминание отправлено.")
    else:
        messages.error(request, f"Не удалось отправить: {notif.error}")
    return redirect("notifications_panel")


# --- Вебхук Telegram (публичный, проверка секретного заголовка) ---
@csrf_exempt
def tg_webhook(request, slug):
    if request.method != "POST":
        return JsonResponse({"ok": False}, status=405)
    t = Tenant.objects.filter(slug=slug, is_active=True).first()
    if t is None:
        return JsonResponse({"ok": False}, status=404)
    with tenant_context(t):
        s = get_settings()
        token = s.telegram_bot_token
        if not token:
            return JsonResponse({"ok": False}, status=404)
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != tg.webhook_secret(token):
            return HttpResponseForbidden("bad secret")
        try:
            update = json.loads(request.body or b"{}")
        except (ValueError, TypeError):
            return JsonResponse({"ok": False}, status=400)
        tg.handle_update(token, update)
    return JsonResponse({"ok": True})
