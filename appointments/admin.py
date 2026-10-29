from django.contrib import admin

from core.adminmixins import TenantModelAdmin
from appointments.models import Appointment, Resource, Service, ServiceCategory


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(TenantModelAdmin):
    list_display = ("name", "tenant", "sort_order")
    list_filter = ("tenant",)


@admin.register(Resource)
class ResourceAdmin(TenantModelAdmin):
    list_display = ("name", "tenant")
    list_filter = ("tenant",)


@admin.register(Service)
class ServiceAdmin(TenantModelAdmin):
    list_display = ("name", "category", "duration_min", "price", "tenant", "is_active")
    list_filter = ("tenant", "category", "is_active")
    search_fields = ("name",)


@admin.register(Appointment)
class AppointmentAdmin(TenantModelAdmin):
    list_display = ("start", "client", "employee", "service", "status", "price", "tenant")
    list_filter = ("tenant", "status", "employee")
    date_hierarchy = "start"
