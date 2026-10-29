"""Маршруты раздела «Сотрудники»: ростер (сайдбар) + управление (настройки)."""
from django.urls import path

from staff import views

urlpatterns = [
    # Ростер — пункт сайдбара
    path("staff/", views.staff_list, name="staff_list"),
    # Управление — в Настройках
    path("settings/staff/", views.staff_manage, name="staff_manage"),
    path("settings/staff/create/", views.staff_create, name="staff_create"),
    path("settings/staff/<int:pk>/edit/", views.staff_edit, name="staff_edit"),
    path("settings/staff/<int:pk>/toggle/", views.staff_toggle, name="staff_toggle"),
]
