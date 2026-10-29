"""
Клиентская база: список и карточка клиента.

Карточка — это наш клин (боль №2): сверху сводка-профиль (автотеги услуг,
ключевые метрики, любимый мастер, статус), zero-click, до ленты визитов.
"""
from collections import Counter
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from appointments.models import Appointment
from clients.models import Client
from core.permissions import requires


# --- Статус клиента по дате последнего визита ---
def _status(last_dt):
    if last_dt is None:
        return ("new", "Новый")
    days = (timezone.now() - last_dt).days
    if days <= 45:
        return ("active", "Активный")
    if days <= 90:
        return ("sleeping", "Спящий")
    return ("lost", "Ушёл")


# --- Список клиентов со сводными цифрами ---
@login_required
@requires("client.view")
def client_list(request):
    q = (request.GET.get("q") or "").strip()
    came = Q(appointments__status=Appointment.STATUS_CAME)
    clients = Client.objects.annotate(
        visits=Count("appointments", filter=came),
        last=Max("appointments__start", filter=came),
    ).order_by("full_name")
    if q:
        clients = clients.filter(Q(full_name__icontains=q) | Q(phone__icontains=q))

    rows = []
    for c in clients:
        code, label = _status(c.last)
        rows.append({"c": c, "visits": c.visits, "last": c.last, "status": code, "status_label": label})

    return render(request, "clients/list.html", {"rows": rows, "q": q, "total": len(rows)})


# --- Карточка клиента: профиль-сводка сверху + лента визитов ---
@login_required
@requires("client.view")
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    appts = list(
        Appointment.objects.filter(client=client)
        .select_related("service", "employee")
        .order_by("-start")
    )
    came = [a for a in appts if a.status == Appointment.STATUS_CAME]

    # Метрики
    ltv = sum((a.price for a in came), 0)
    visits = len(came)
    avg_check = round(ltv / visits) if visits else 0
    last_dt = came[0].start if came else None
    code, label = _status(last_dt)

    # Автотеги по услугам (из состоявшихся визитов)
    svc_counter = Counter(a.service.name for a in came if a.service)
    tags = svc_counter.most_common()

    # Любимый мастер (к кому чаще ходил)
    emp_counter = Counter(a.employee.full_name for a in came)
    favorite = emp_counter.most_common(1)[0][0] if emp_counter else None

    context = {
        "client": client,
        "appts": appts,
        "ltv": round(ltv),
        "visits": visits,
        "avg_check": avg_check,
        "last_dt": last_dt,
        "status": code,
        "status_label": label,
        "tags": tags,
        "favorite": favorite,
    }
    return render(request, "clients/detail.html", context)
