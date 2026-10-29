from django.contrib import admin

from core.adminmixins import TenantModelAdmin
from staff.models import Employee


@admin.register(Employee)
class EmployeeAdmin(TenantModelAdmin):
    list_display = ("full_name", "specialization", "tenant", "is_active", "sort_order")
    list_filter = ("tenant", "is_active")
    search_fields = ("full_name", "specialization")
