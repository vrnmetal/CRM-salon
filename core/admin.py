"""
Админка Django — служебный инструмент разработчика/провайдера (не парадный экран).
Здесь намеренно просто: удобно управлять тенантами, пользователями, ролями, аудитом.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from core.models import AuditLog, Role, Tenant, User


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "plan", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "brand_name")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "preset_code")
    list_filter = ("tenant",)
    search_fields = ("name",)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # Добавляем наши поля к стандартной админке пользователя
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Салон", {"fields": ("tenant", "role", "is_provider_admin", "show_hints")}),
    )
    list_display = ("username", "tenant", "role", "is_provider_admin", "is_staff")
    list_filter = ("tenant", "is_provider_admin", "is_staff")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    # Аудит только для чтения (append-only, не правим руками)
    list_display = ("created_at", "action", "tenant", "user", "target")
    list_filter = ("action", "tenant")
    search_fields = ("action", "target")
    readonly_fields = ("tenant", "user", "action", "target", "meta", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
