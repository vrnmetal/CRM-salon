"""Маршруты публичного портала онлайн-записи."""
from django.urls import path

from booking import views

urlpatterns = [
    path("book/<slug:slug>/", views.book_services, name="book_services"),
    path("book/<slug:slug>/s/<int:service_id>/", views.book_slots, name="book_slots"),
    path("book/<slug:slug>/s/<int:service_id>/form/", views.book_form, name="book_form"),
    path("book/<slug:slug>/confirm/", views.book_confirm, name="book_confirm"),
    path("book/<slug:slug>/done/<int:appt_id>/", views.book_done, name="book_done"),
]
