"""Маршруты клиентской базы."""
from django.urls import path

from clients import views

urlpatterns = [
    path("clients/", views.client_list, name="client_list"),
    path("clients/search/", views.client_search, name="client_search"),
    path("clients/<int:pk>/", views.client_detail, name="client_detail"),
]
