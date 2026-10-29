"""Маршруты клиентской базы."""
from django.urls import path

from clients import views

urlpatterns = [
    path("clients/", views.client_list, name="client_list"),
    path("clients/<int:pk>/", views.client_detail, name="client_detail"),
]
