"""Маршруты модуля записей: журнал и быстрая запись."""
from django.urls import path

from appointments import views

urlpatterns = [
    path("journal/", views.journal, name="journal"),
    path("journal/add/", views.quick_add, name="appointment_add"),
    path("journal/appt/<int:pk>/", views.appointment_detail, name="appointment_detail"),
]
