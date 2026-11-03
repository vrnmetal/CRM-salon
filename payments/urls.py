"""Маршруты оплаты."""
from django.urls import path

from payments import views

urlpatterns = [
    path("journal/appt/<int:appt_pk>/pay/", views.payment_charge, name="payment_charge"),
    path("settings/payment/", views.payment_settings, name="payment_settings"),
    path("pay/<int:pk>/confirm/", views.payment_confirm, name="payment_confirm"),
    path("pay/<int:pk>/cancel/", views.payment_cancel, name="payment_cancel"),
]
