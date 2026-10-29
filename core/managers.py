"""
Менеджеры и базовая модель для мультитенантности (row-level изоляция по tenant_id).

TenantModel — абстрактная база: у всех «клиентских» моделей есть FK на тенанта.
  * objects      — автоматически фильтрует по текущему тенанту (безопасно по умолчанию)
  * all_objects  — БЕЗ фильтра, только для провайдерской админки/миграций/фона

Один баг в фильтре = чужая база утекла, поэтому фильтрация централизована здесь,
а не копируется по вьюхам.
"""
from django.db import models

from core.tenancy import get_current_tenant


# --- Менеджер, который режет queryset по текущему тенанту ---
class TenantManager(models.Manager):
    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_current_tenant()
        if tenant is not None:
            # Есть активный тенант — показываем только его строки
            return qs.filter(tenant=tenant)
        # Тенанта в контексте нет (например, провайдерский слой без выбранного тенанта):
        # по умолчанию НИЧЕГО не отдаём — безопаснее, чем отдать всё.
        return qs.none()


# --- Абстрактная база для всех клиентских (принадлежащих тенанту) моделей ---
class TenantModel(models.Model):
    # Привязка строки к тенанту. index — потому что фильтруем по нему всегда.
    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        db_index=True,
        verbose_name="Тенант",
    )

    # По умолчанию — тенант-ограниченный менеджер
    objects = TenantManager()
    # Сквозной доступ (провайдер/фон) — осознанно и явно
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # Страховка: если тенант не проставлен явно — берём из контекста запроса.
        if self.tenant_id is None:
            current = get_current_tenant()
            if current is not None:
                self.tenant = current
        super().save(*args, **kwargs)
