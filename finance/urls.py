"""Маршруты модуля «Финансы и касса»."""
from django.urls import path

from finance import views

urlpatterns = [
    path("finance/", views.finance_home, name="finance_home"),
]
