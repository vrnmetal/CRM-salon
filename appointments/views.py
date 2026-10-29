"""
Журнал (день, колонки-мастера) и быстрая запись.

Дизайн-принцип: журнал открывается сразу на сегодня, быстрая запись — короткая
форма. Данные изолированы по тенанту автоматически (TenantManager).
"""
from datetime import date as date_cls, datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from appointments.forms import QuickAppointmentForm
from appointments.models import Appointment
from clients.models import Client
from core.permissions import requires
from staff.models import Employee


# --- Разбор даты из ?date=YYYY-MM-DD (по умолчанию сегодня) ---
def _parse_date(request):
    raw = request.GET.get("date")
    if raw:
        try:
            return date_cls.fromisoformat(raw)
        except ValueError:
            pass
    return timezone.localdate()


# Параметры временной сетки журнала
DAY_START_HOUR = 9       # начало рабочего дня (верх сетки)
DAY_END_HOUR = 22        # конец (низ сетки)
HOUR_PX = 56             # высота одного часа в пикселях
MIN_BLOCK_PX = 30        # минимальная высота блока (чтобы короткие были читаемы)


# --- Журнал записей: временная сетка, колонки-мастера, блоки на своих местах ---
@login_required
@requires("appointment.view")
def journal(request):
    day = _parse_date(request)

    # Активные мастера — колонки журнала
    employees = list(Employee.objects.filter(is_active=True))

    appts = (
        Appointment.objects.filter(start__date=day)
        .select_related("client", "employee", "service")
        .order_by("start")
    )

    # Раскладываем записи по мастерам, считая позицию каждого блока по времени.
    # Промежутки между записями становятся видимым пустым пространством.
    by_employee = {e.id: [] for e in employees}
    for a in appts:
        local = timezone.localtime(a.start)
        offset_min = (local.hour - DAY_START_HOUR) * 60 + local.minute
        top = offset_min * HOUR_PX / 60
        height = max(a.duration_min * HOUR_PX / 60, MIN_BLOCK_PX)
        by_employee.setdefault(a.employee_id, []).append({
            "appt": a,
            "top": round(top),
            "height": round(height),
            "end": local + timedelta(minutes=a.duration_min),
        })

    columns = [{"employee": e, "blocks": by_employee.get(e.id, [])} for e in employees]

    # Часовые отметки для линейки времени слева
    hours = [
        {"label": f"{h:02d}:00", "top": round((h - DAY_START_HOUR) * HOUR_PX)}
        for h in range(DAY_START_HOUR, DAY_END_HOUR + 1)
    ]
    grid_height = (DAY_END_HOUR - DAY_START_HOUR) * HOUR_PX

    context = {
        "day": day,
        "prev_day": (day - timedelta(days=1)).isoformat(),
        "next_day": (day + timedelta(days=1)).isoformat(),
        "today": timezone.localdate().isoformat(),
        "columns": columns,
        "total": appts.count(),
        "hours": hours,
        "grid_height": grid_height,
        "hour_px": HOUR_PX,
    }
    return render(request, "appointments/journal.html", context)


# --- Детали записи (открывается кликом по блоку в журнале) ---
@login_required
@requires("appointment.view")
def appointment_detail(request, pk):
    # objects — тенант-ограниченный менеджер, чужую запись не отдаст
    from django.shortcuts import get_object_or_404

    appt = get_object_or_404(
        Appointment.objects.select_related("client", "employee", "service"), pk=pk
    )
    return render(request, "appointments/detail.html", {"a": appt})


# --- Быстрая запись: короткая форма -> создаёт/находит клиента и пишет запись ---
@login_required
@requires("appointment.create")
def quick_add(request):
    if request.method == "POST":
        form = QuickAppointmentForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            # Собираем дату+время в aware-datetime (TZ проекта)
            start = timezone.make_aware(datetime.combine(cd["date"], cd["time"]))

            # Дедуп клиента по телефону в пределах тенанта
            phone = cd["client_phone"].strip()
            client, created = Client.objects.get_or_create(
                phone=phone, defaults={"full_name": cd["client_name"].strip() or phone}
            )
            # Если имя пришло, а у клиента пусто — дозаполним
            if cd["client_name"].strip() and not client.full_name:
                client.full_name = cd["client_name"].strip()
                client.save(update_fields=["full_name"])

            service = cd["service"]
            # Создаём запись; длительность и цену берём из услуги
            Appointment.objects.create(
                client=client,
                employee=cd["employee"],
                service=service,
                start=start,
                duration_min=service.duration_min,
                price=service.price,
                pdn_consent=cd["pdn_consent"],
            )
            # Возвращаемся в журнал на день записи
            url = reverse("journal") + f"?date={cd['date'].isoformat()}"
            return redirect(url)
    else:
        # Предзаполним дату выбранным днём журнала (или сегодня)
        form = QuickAppointmentForm(initial={"date": _parse_date(request)})

    return render(request, "appointments/quick_add.html", {"form": form})
