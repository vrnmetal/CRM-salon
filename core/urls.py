"""Маршруты ядра: вход/выход, домашний роутер, дашборд, журнал, доступы, профиль."""
from django.contrib.auth import views as auth_views
from django.urls import path

from core import views

urlpatterns = [
    # Вход/выход (стандартные вьюхи Django со своими шаблонами)
    path("login/", auth_views.LoginView.as_view(template_name="core/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
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
    # Тумблер подсказок
    path("profile/hints/toggle/", views.toggle_hints, name="toggle_hints"),
]
