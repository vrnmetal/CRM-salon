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

from appointments.forms import EditAppointmentForm, QuickAppointmentForm
from appointments.models import Appointment, AppointmentService, Service
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

    # Линия текущего времени — только если смотрим сегодня и сейчас в пределах сетки
    now_top = None
    now_label = None
    if day == timezone.localdate():
        now = timezone.localtime()
        mins = (now.hour - DAY_START_HOUR) * 60 + now.minute
        if 0 <= mins <= (DAY_END_HOUR - DAY_START_HOUR) * 60:
            now_top = round(mins * HOUR_PX / 60)
            now_label = now.strftime("%H:%M")

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
        "now_top": now_top,
        "now_label": now_label,
    }
    return render(request, "appointments/journal.html", context)


# --- Детали записи (открывается кликом по блоку в журнале) ---
@login_required
@requires("appointment.view")
def appointment_detail(request, pk):
    from django.shortcuts import get_object_or_404

    appt = get_object_or_404(
        Appointment.objects.select_related("client", "employee", "service"), pk=pk
    )
    lines = appt.lines.select_related("service").all()
    return render(request, "appointments/detail.html", {"a": appt, "lines": lines})


# --- Редактирование записи ---
@login_required
@requires("appointment.edit")
def appointment_edit(request, pk):
    from django.shortcuts import get_object_or_404

    appt = get_object_or_404(Appointment, pk=pk)

    if request.method == "POST":
        form = EditAppointmentForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            # Клиент: находим/создаём по телефону (данные подтягиваются из базы)
            phone = cd["client_phone"].strip()
            client, _ = Client.objects.get_or_create(
                phone=phone, defaults={"full_name": cd["client_name"].strip() or phone}
            )
            if cd["client_name"].strip():
                client.full_name = cd["client_name"].strip()
                client.save(update_fields=["full_name"])

            services = form.chosen_services()
            # Пересобираем строки услуг
            appt.lines.all().delete()
            total_from_services = 0
            for s in services:
                AppointmentService.objects.create(appointment=appt, service=s, price=s.price)
                total_from_services += s.price

            appt.client = client
            appt.employee = cd["employee"]
            appt.service = services[0] if services else None  # первая — для компактного вида
            appt.start = timezone.make_aware(datetime.combine(cd["date"], cd["time"]))
            appt.duration_min = sum(s.duration_min for s in services) or appt.duration_min
            appt.status = cd["status"]
            # Цена: если указали вручную — она (скидка/надбавка), иначе сумма услуг
            appt.price = cd["price"] if cd["price"] is not None else total_from_services
            appt.comment = cd["comment"].strip()
            appt.save()

            return redirect(reverse("appointment_detail", args=[appt.id]))
    else:
        # Префилл из текущей записи
        local = timezone.localtime(appt.start)
        initial = {
            "client_phone": appt.client.phone,
            "client_name": appt.client.full_name,
            "employee": appt.employee_id,
            "date": local.date(),
            "time": local.time().strftime("%H:%M"),
            "status": appt.status,
            "price": appt.price,
            "comment": appt.comment,
        }
        # Префилл выбранных услуг из строк
        for idx, line in enumerate(appt.lines.all(), start=1):
            if idx <= 4:
                initial[f"service_{idx}"] = line.service_id
        form = EditAppointmentForm(initial=initial)

    # Список клиентов для автоподстановки (телефон → имя)
    clients = list(Client.objects.values("phone", "full_name"))
    return render(request, "appointments/edit.html", {"form": form, "a": appt, "clients_json": clients})


# --- Удаление записи ---
@login_required
@requires("appointment.delete")
def appointment_delete(request, pk):
    from django.shortcuts import get_object_or_404

    if request.method != "POST":
        return redirect(reverse("appointment_detail", args=[pk]))
    appt = get_object_or_404(Appointment, pk=pk)
    day = timezone.localtime(appt.start).date().isoformat()
    appt.delete()
    return redirect(reverse("journal") + f"?date={day}")


# --- Список услуг (управление из интерфейса, не только админка) ---
@login_required
@requires("service.view")
def service_list(request):
    from appointments.models import ServiceCategory

    if request.method == "POST":
        # Создание услуги (требует отдельного права)
        from core.permissions import has_perm
        if not has_perm(request.user, "service.create"):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("Нет права: service.create")
        name = (request.POST.get("name") or "").strip()
        if name:
            Service.objects.create(
                name=name,
                duration_min=int(request.POST.get("duration_min") or 60),
                price=request.POST.get("price") or 0,
            )
        return redirect("service_list")

    services = Service.objects.select_related("category").all()
    return render(request, "appointments/services.html", {"services": services})


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
            appt = Appointment.objects.create(
                client=client,
                employee=cd["employee"],
                service=service,
                start=start,
                duration_min=service.duration_min,
                price=service.price,
                pdn_consent=cd["pdn_consent"],
            )
            # Строка услуги (запись может позже получить ещё услуги при редактировании)
            AppointmentService.objects.create(appointment=appt, service=service, price=service.price)
            # Возвращаемся в журнал на день записи
            url = reverse("journal") + f"?date={cd['date'].isoformat()}"
            return redirect(url)
    else:
        # Предзаполним дату выбранным днём журнала (или сегодня)
        form = QuickAppointmentForm(initial={"date": _parse_date(request)})

    return render(request, "appointments/quick_add.html", {"form": form})
