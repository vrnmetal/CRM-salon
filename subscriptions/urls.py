"""Маршруты модуля «Абонементы и сертификаты»."""
from django.urls import path

from subscriptions import views

urlpatterns = [
    path("subscriptions/", views.plans_home, name="subs_plans"),
    path("subscriptions/new/", views.plan_create, name="subs_plan_create"),
    path("subscriptions/<int:pk>/toggle/", views.plan_toggle, name="subs_plan_toggle"),
    path("subscriptions/sell/<int:client_pk>/", views.sell, name="subs_sell"),
    path("subscriptions/redeem/<int:pk>/", views.redeem, name="subs_redeem"),
]
