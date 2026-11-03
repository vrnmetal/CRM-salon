"""Маршруты модуля «Склад и тех. карты»."""
from django.urls import path

from stock import views

urlpatterns = [
    path("stock/", views.stock_home, name="stock_home"),
    path("stock/material/new/", views.material_create, name="material_create"),
    path("stock/material/<int:pk>/edit/", views.material_edit, name="material_edit"),
    path("stock/material/<int:pk>/move/", views.material_move, name="material_move"),
    path("stock/techcards/", views.techcards, name="techcards"),
    path("stock/techcards/<int:service_pk>/", views.service_card, name="service_card"),
    # Расход материалов по конкретной записи
    path("stock/appt/<int:appt_pk>/fill/", views.appt_fill, name="appt_fill"),
    path("stock/appt/<int:appt_pk>/mat/set/", views.appt_mat_set, name="appt_mat_set"),
    path("stock/appt/mat/<int:pk>/remove/", views.appt_mat_remove, name="appt_mat_remove"),
]

