"""Маршруты раздела «Сотрудники»."""
from django.urls import path

from staff import views

urlpatterns = [
    path("staff/", views.staff_list, name="staff_list"),
]
