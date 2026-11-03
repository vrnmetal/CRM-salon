"""
Авто-списание расходников при проведении визита.

Когда запись переходит в статус «пришёл» — списываем материалы по тех. картам
её услуг. Идемпотентно: если по записи уже есть движения, повторно не списываем
(ссылка appointment в StockMovement). Работает только если у тенанта включён
модуль «stock».
"""
from django.db.models import F
from django.db.models.signals import post_save
from django.dispatch import receiver

from appointments.models import Appointment
from core.modules import is_module_enabled


@receiver(post_save, sender=Appointment)
def writeoff_on_came(sender, instance, **kwargs):
    if instance.status != Appointment.STATUS_CAME:
        return
    tenant = getattr(instance, "tenant", None)
    if tenant is None or not is_module_enabled(tenant, "stock"):
        return

    from stock.models import AppointmentMaterial, Material, StockMovement, TechCardItem

    # Уже списывали по этой записи — выходим (идемпотентность)
    if StockMovement.all_objects.filter(appointment=instance).exists():
        return

    def writeoff(material, spent, note):
        StockMovement.objects.create(
            tenant=tenant, material=material, delta=-spent,
            reason=StockMovement.CONSUME, appointment=instance, note=note,
        )
        Material.all_objects.filter(pk=material.pk).update(quantity=F("quantity") - spent)

    # 1) Если задан фактический расход по записи — списываем строго по нему
    overrides = list(AppointmentMaterial.all_objects.filter(appointment=instance).select_related("material"))
    if overrides:
        for om in overrides:
            writeoff(om.material, om.qty, "факт. расход по записи")
        return

    # 2) Иначе — по тех. картам услуг визита (с учётом нормы потерь)
    from appointments.models import AppointmentService
    lines = AppointmentService.all_objects.filter(appointment=instance).select_related("service")
    for line in lines:
        if not line.service_id:
            continue
        for item in TechCardItem.all_objects.filter(tenant=tenant, service_id=line.service_id).select_related("material"):
            writeoff(item.material, item.effective_qty, line.service.name if line.service else "")
