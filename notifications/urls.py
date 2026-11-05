from django.urls import path

from notifications import views

urlpatterns = [
    path("notifications/", views.panel, name="notifications_panel"),
    path("notifications/settings/", views.panel, name="notification_settings"),  # общие настройки = POST на Обзор
    path("notifications/telegram/", views.channel_telegram, name="notification_telegram"),
    path("notifications/sms/", views.channel_sms, name="notification_sms"),
    path("notifications/send/<int:appt_id>/", views.send, name="notification_send"),
    # Вебхук Telegram (публичный, проверка секретного заголовка)
    path("tg/<slug:slug>/", views.tg_webhook, name="tg_webhook"),
]
