"""Маршруты провайдерской панели (control plane над всеми тенантами)."""
from django.urls import path

from provider import views

urlpatterns = [
    path("provider/", views.home, name="provider_home"),
    path("provider/audit/", views.audit_log, name="provider_audit"),
    path("provider/new/", views.tenant_create, name="provider_tenant_create"),
    path("provider/t/<int:pk>/", views.tenant_detail, name="provider_tenant"),
    path("provider/t/<int:pk>/toggle/", views.tenant_toggle, name="provider_tenant_toggle"),
    path("provider/t/<int:pk>/modules/", views.tenant_modules, name="provider_tenant_modules"),
    path("provider/t/<int:pk>/billing/", views.tenant_billing, name="provider_tenant_billing"),
    path("provider/t/<int:pk>/domain/", views.tenant_domain, name="provider_tenant_domain"),
    path("provider/t/<int:pk>/domain/verify/", views.tenant_domain_verify, name="provider_tenant_domain_verify"),
    path("provider/t/<int:pk>/impersonate/", views.impersonate_start, name="provider_impersonate"),
    path("provider/impersonate/stop/", views.impersonate_stop, name="provider_impersonate_stop"),
    # Управление аккаунтами салона (сброс пароля, смена логина)
    path("provider/account/<int:pk>/reset/", views.account_reset, name="provider_account_reset"),
    path("provider/account/<int:pk>/rename/", views.account_rename, name="provider_account_rename"),
]
