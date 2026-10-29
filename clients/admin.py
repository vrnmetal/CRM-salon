from django.contrib import admin

from core.adminmixins import TenantModelAdmin
from clients.models import Client


@admin.register(Client)
class ClientAdmin(TenantModelAdmin):
    list_display = ("full_name", "phone", "tenant", "created_at")
    list_filter = ("tenant",)
    search_fields = ("full_name", "phone", "email")
