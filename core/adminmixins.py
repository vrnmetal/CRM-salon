"""
База для админок бизнес-моделей (TenantModel).

В Django-админке контекста тенанта нет, поэтому обычный `objects` (тенант-фильтр)
вернул бы пусто. Здесь используем all_objects — провайдер/разработчик видит все
строки всех тенантов (это служебный инструмент). Колонка тенанта выводится явно.
"""
from django.contrib import admin


class TenantModelAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        # Сквозной доступ в админке (минуя тенант-фильтр)
        return self.model.all_objects.all()
