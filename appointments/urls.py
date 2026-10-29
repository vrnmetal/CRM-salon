"""Маршруты модуля записей: журнал и быстрая запись."""
from django.urls import path

from appointments import views

urlpatterns = [
    path("journal/", views.journal, name="journal"),
    path("journal/add/", views.quick_add, name="appointment_add"),
    path("journal/appt/<int:pk>/", views.appointment_detail, name="appointment_detail"),
    path("journal/appt/<int:pk>/edit/", views.appointment_edit, name="appointment_edit"),
    path("journal/appt/<int:pk>/delete/", views.appointment_delete, name="appointment_delete"),
    path("services/", views.service_list, name="service_list"),
]
