"""Маршруты модуля «Расчёт зарплат»."""
from django.urls import path

from payroll import views

urlpatterns = [
    path("payroll/", views.payroll_home, name="payroll_home"),
    path("payroll/schemes/", views.schemes_list, name="payroll_schemes"),
    path("payroll/schemes/new/", views.scheme_new, name="payroll_scheme_new"),
    path("payroll/schemes/<int:pk>/", views.scheme_edit, name="payroll_scheme_edit"),
    path("payroll/assign/<int:employee_pk>/", views.assign_scheme, name="payroll_assign"),
]
