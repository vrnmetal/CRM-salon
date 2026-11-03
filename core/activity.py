"""
История действий с возможностью отмены (generic-слой через сигналы моделей).

Идея: на каждое изменение отслеживаемой модели пишем запись ActivityLog со
снимком состояния «до» (сериализатор Django). Откат восстанавливает снимок:
  • создание → удаляем объект;
  • изменение → возвращаем прежние значения полей;
  • удаление → вставляем объект обратно.

Ограничения (честно): откат затрагивает ОДИН объект записи. Каскадно удалённые
дочерние строки при откате удаления не восстанавливаются; массовые .update()
(напр. движения склада) сигналами не ловятся. Для таких — своя логика позже.
"""
import threading

from django.apps import apps
from django.core.serializers import deserialize, serialize
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.utils import timezone

from core import tenancy

# Какие модели пишем в историю (бизнес-сущности; служебное/шумное не трогаем)
TRACKED = {
    "appointments.Appointment", "appointments.AppointmentService",
    "appointments.Service", "appointments.ServiceCategory", "appointments.Resource",
    "clients.Client",
    "staff.Employee",
    "stock.Material", "stock.TechCardItem",
    "subscriptions.SubscriptionPlan", "subscriptions.ClientSubscription",
    "payments.Payment",
    "core.User", "core.Role",
}

# Человекочитаемые имена моделей для интерфейса
MODEL_LABELS = {
    "appointments.Appointment": "Запись",
    "appointments.AppointmentService": "Услуга в записи",
    "appointments.Service": "Услуга",
    "appointments.ServiceCategory": "Категория услуг",
    "appointments.Resource": "Ресурс",
    "clients.Client": "Клиент",
    "staff.Employee": "Сотрудник",
    "stock.Material": "Материал",
    "stock.TechCardItem": "Строка тех. карты",
    "subscriptions.SubscriptionPlan": "Продукт (абонемент)",
    "subscriptions.ClientSubscription": "Абонемент клиента",
    "payments.Payment": "Оплата",
    "core.User": "Аккаунт",
    "core.Role": "Роль",
}

# Флаг подавления: во время отката не логируем восстановление
_state = threading.local()


def _suppressed():
    return getattr(_state, "suppress", False)


class suppress_logging:
    def __enter__(self):
        _state.suppress = True

    def __exit__(self, *a):
        _state.suppress = False


def _label(instance):
    return f"{instance._meta.app_label}.{instance.__class__.__name__}"


def human_model(model_label):
    return MODEL_LABELS.get(model_label, model_label)


# ============================================================================
# Сигналы
# ============================================================================
def _pre_save(sender, instance, **kwargs):
    label = _label(instance)
    if label not in TRACKED or _suppressed():
        return
    if instance.pk:
        old = sender._base_manager.filter(pk=instance.pk).first()
        instance._act_before = serialize("json", [old]) if old else ""
    else:
        instance._act_before = ""


# Технические обновления, которые не считаем действием (чтобы не засорять историю)
_NOISE_FIELDS = {"last_login", "show_hints"}


def _is_noise_update(kwargs):
    uf = kwargs.get("update_fields")
    return bool(uf) and set(uf) <= _NOISE_FIELDS


def _post_save(sender, instance, created, **kwargs):
    label = _label(instance)
    if label not in TRACKED or _suppressed() or _is_noise_update(kwargs):
        return
    actor = tenancy.get_current_user()
    tenant = tenancy.get_current_tenant() or getattr(instance, "tenant", None)
    if actor is None or tenant is None:
        return  # действия без пользователя (сид/фон) не пишем
    from core.models import ActivityLog
    ActivityLog.objects.create(
        tenant=tenant, actor=actor,
        action=ActivityLog.CREATE if created else ActivityLog.UPDATE,
        model_label=label, object_pk=str(instance.pk),
        object_repr=str(instance)[:250],
        before_json="" if created else getattr(instance, "_act_before", ""),
    )


def _pre_delete(sender, instance, **kwargs):
    label = _label(instance)
    if label not in TRACKED or _suppressed():
        return
    instance._act_before_del = serialize("json", [instance])


def _post_delete(sender, instance, **kwargs):
    label = _label(instance)
    if label not in TRACKED or _suppressed():
        return
    actor = tenancy.get_current_user()
    tenant = tenancy.get_current_tenant() or getattr(instance, "tenant", None)
    if actor is None or tenant is None:
        return
    from core.models import ActivityLog
    ActivityLog.objects.create(
        tenant=tenant, actor=actor, action=ActivityLog.DELETE,
        model_label=label, object_pk=str(instance.pk),
        object_repr=str(instance)[:250],
        before_json=getattr(instance, "_act_before_del", ""),
    )


def connect():
    pre_save.connect(_pre_save, dispatch_uid="act_pre_save")
    post_save.connect(_post_save, dispatch_uid="act_post_save")
    pre_delete.connect(_pre_delete, dispatch_uid="act_pre_delete")
    post_delete.connect(_post_delete, dispatch_uid="act_post_delete")


# ============================================================================
# Откат
# ============================================================================
def undo(entry, user):
    """Отменить действие. Возвращает (ok, message)."""
    if entry.undone:
        return False, "Это действие уже отменено."

    try:
        model = apps.get_model(entry.model_label)
    except LookupError:
        return False, "Модель действия не найдена."

    from core.models import ActivityLog

    with suppress_logging():
        if entry.action == ActivityLog.CREATE:
            obj = model._base_manager.filter(pk=entry.object_pk).first()
            if obj is not None:
                obj.delete()
        elif entry.action in (ActivityLog.UPDATE, ActivityLog.DELETE):
            if not entry.before_json:
                return False, "Нет снимка для восстановления."
            for d in deserialize("json", entry.before_json):
                d.save()  # update вернёт поля, delete вставит объект заново

    entry.undone = True
    entry.undone_at = timezone.now()
    entry.undone_by = user
    entry.save(update_fields=["undone", "undone_at", "undone_by"])
    return True, "Действие отменено."
