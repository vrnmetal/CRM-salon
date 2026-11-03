"""Маршруты ядра: вход/выход, домашний роутер, дашборд, журнал, доступы, профиль."""
from django.contrib.auth import views as auth_views
from django.urls import path

from core import views

urlpatterns = [
    # Вход (двухшаговый: пароль → при 2FA код), выход
    path("login/", views.login_view, name="login"),
    path("login/2fa/", views.login_2fa, name="login_2fa"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Безопасность (2FA) провайдерского аккаунта
    path("security/2fa/", views.security_2fa, name="security_2fa"),
    # Домашний роутер по роли
    path("", views.home, name="home"),
    # Дашборд (журнал живёт в приложении appointments)
    path("dashboard/", views.dashboard, name="dashboard"),
    # Сквозной поиск (клиенты/сотрудники/услуги)
    path("search/", views.global_search, name="global_search"),
    # Раздел «Настройки» собственника
    path("settings/", views.settings_home, name="settings_home"),
    path("settings/access/", views.access_settings, name="access_settings"),
    path("settings/accounts/", views.accounts, name="accounts"),
    path("settings/accounts/<int:pk>/access/", views.account_access, name="account_access"),
    path("settings/accounts/<int:pk>/preset/", views.account_apply_preset, name="account_apply_preset"),
    path("settings/accounts/<int:pk>/delete/", views.account_delete, name="account_delete"),
    path("settings/branding/", views.branding_settings, name="branding_settings"),
    # История действий (с отменой)
    path("history/", views.history, name="history"),
    path("history/<int:pk>/undo/", views.history_undo, name="history_undo"),
    # Тумблер подсказок
    path("profile/hints/toggle/", views.toggle_hints, name="toggle_hints"),
]
