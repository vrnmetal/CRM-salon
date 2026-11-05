"""
Здоровье данных — клин против «грязной базы» (главная боль YCLIENTS).

Телефон уникален в пределах тенанта, поэтому точные дубли невозможны. Но дубли
приходят из-за РАЗНЫХ ФОРМАТОВ номера (импорт, Яндекс.Карты, ручной ввод):
«+79160000001», «89160000001», «9160000001» — один человек, три строки. Ловим их
по нормализованному номеру и предлагаем слияние с переносом истории.

Работает в текущем tenant_context.
"""
from collections import defaultdict

from django.db.models import Count

from clients.models import Client


def normalize_phone(raw):
    """Строка телефона → 10 цифр национального номера, или None если не распознан."""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if len(digits) == 11 and digits[0] in ("7", "8"):
        digits = digits[1:]
    if len(digits) == 10:
        return digits
    return None


def duplicate_groups():
    """Группы клиентов с одинаковым нормализованным телефоном (по 2+ в группе).

    Внутри группы клиенты отсортированы: первым — предлагаемый основной (больше
    всего визитов, при равенстве — созданный раньше)."""
    clients = list(Client.objects.annotate(n_appts=Count("appointments")))
    groups = defaultdict(list)
    for c in clients:
        key = normalize_phone(c.phone)
        if key:
            groups[key].append(c)
    result = []
    for key, members in groups.items():
        if len(members) > 1:
            members.sort(key=lambda c: (-c.n_appts, c.created_at))
            result.append({"phone": key, "clients": members})
    result.sort(key=lambda g: len(g["clients"]), reverse=True)
    return result


def problem_clients():
    """Клиенты с «мусорными» данными: кривой телефон, нет имени, имя = телефон."""
    probs = []
    for c in Client.objects.annotate(n_appts=Count("appointments")):
        issues = []
        if normalize_phone(c.phone) is None:
            issues.append("некорректный телефон")
        name = (c.full_name or "").strip()
        if not name:
            issues.append("нет имени")
        elif name == (c.phone or "").strip():
            issues.append("имя = телефон")
        if issues:
            probs.append({"client": c, "issues": issues})
    return probs


def negative_stock(tenant):
    """Материалы с отрицательным остатком (если включён модуль склада)."""
    if not tenant or not tenant.is_module_on("stock"):
        return []
    from stock.models import Material
    return list(Material.objects.filter(quantity__lt=0))


def merge_clients(primary, dups):
    """Сливает дубли в основного: переносит записи и абонементы, дозаполняет пустые
    поля основного, удаляет дубли. Возвращает число слитых."""
    from appointments.models import Appointment
    ids = [d.id for d in dups if d.id != primary.id]
    if not ids:
        return 0

    Appointment.objects.filter(client_id__in=ids).update(client=primary)
    try:
        from subscriptions.models import ClientSubscription
        ClientSubscription.objects.filter(client_id__in=ids).update(client=primary)
    except Exception:
        pass

    changed = False
    for d in dups:
        if d.id == primary.id:
            continue
        if not primary.email and d.email:
            primary.email = d.email
            changed = True
        if not primary.note and d.note:
            primary.note = d.note
            changed = True
    if changed:
        primary.save(update_fields=["email", "note"])

    Client.objects.filter(id__in=ids).delete()
    return len(ids)
