"""
Аналитика по записям: сводка за период + выгрузка в Excel.

Считается поверх журнала (Appointment) в текущем tenant_context (его ставит
middleware на каждый запрос), поэтому обычный Appointment.objects уже изолирован
по тенанту. Один источник расчёта для экрана и для .xlsx — цифры всегда совпадают.
"""
from io import BytesIO

from django.db.models import Count, Q, Sum
from django.utils import timezone

from appointments.models import Appointment

A = Appointment

STATUS_LABELS = dict(A.STATUS_CHOICES)
SOURCE_LABELS = dict(A.SOURCE_CHOICES)
SOURCE_ORDER = [A.SOURCE_JOURNAL, A.SOURCE_PORTAL, A.SOURCE_EXTERNAL]


def _pct(part, whole):
    return round(100 * part / whole) if whole else 0


def build_report(start, end, label="", key=""):
    """Собирает все метрики за период [start; end] (даты включительно)."""
    qs = A.objects.filter(start__date__gte=start, start__date__lte=end)
    came_qs = qs.filter(status=A.STATUS_CAME)

    total = qs.count()
    came = came_qs.count()
    noshow = qs.filter(status=A.STATUS_NOSHOW).count()
    waiting = qs.filter(status__in=[A.STATUS_WAIT, A.STATUS_CONFIRMED]).count()
    revenue = int(came_qs.aggregate(s=Sum("price"))["s"] or 0)
    avg_check = int(revenue / came) if came else 0
    online = qs.filter(source__in=[A.SOURCE_PORTAL, A.SOURCE_EXTERNAL]).count()

    totals = {
        "total": total,
        "came": came,
        "waiting": waiting,
        "noshow": noshow,
        "revenue": revenue,
        "avg_check": avg_check,
        "noshow_rate": _pct(noshow, total),
        "online": online,
        "online_rate": _pct(online, total),
    }

    # По статусам
    by_status = []
    for code, lbl in A.STATUS_CHOICES:
        c = qs.filter(status=code).count()
        if c:
            by_status.append({"code": code, "label": lbl, "count": c, "pct": _pct(c, total)})

    # По источникам (кол-во + выручка пришедших)
    by_source = []
    for code in SOURCE_ORDER:
        c = qs.filter(source=code).count()
        rev = int(came_qs.filter(source=code).aggregate(s=Sum("price"))["s"] or 0)
        if c:
            by_source.append({
                "code": code, "label": SOURCE_LABELS.get(code, code),
                "count": c, "pct": _pct(c, total), "revenue": rev,
            })

    # По мастерам
    by_master = []
    mrows = (qs.values("employee_id", "employee__full_name")
             .annotate(
                 total=Count("id"),
                 came=Count("id", filter=Q(status=A.STATUS_CAME)),
                 noshow=Count("id", filter=Q(status=A.STATUS_NOSHOW)),
                 revenue=Sum("price", filter=Q(status=A.STATUS_CAME)),
             ))
    for r in mrows:
        by_master.append({
            "name": r["employee__full_name"] or "—",
            "total": r["total"],
            "came": r["came"],
            "noshow": r["noshow"],
            "revenue": int(r["revenue"] or 0),
        })
    by_master.sort(key=lambda x: x["revenue"], reverse=True)

    # По услугам
    by_service = []
    srows = (qs.values("service_id", "service__name")
             .annotate(
                 total=Count("id"),
                 came=Count("id", filter=Q(status=A.STATUS_CAME)),
                 revenue=Sum("price", filter=Q(status=A.STATUS_CAME)),
             ))
    for r in srows:
        by_service.append({
            "name": r["service__name"] or "— без услуги —",
            "total": r["total"],
            "came": r["came"],
            "revenue": int(r["revenue"] or 0),
        })
    by_service.sort(key=lambda x: x["revenue"], reverse=True)

    # По дням (для выгрузки и графика)
    by_day = []
    drows = (qs.values("start__date")
             .annotate(
                 total=Count("id"),
                 came=Count("id", filter=Q(status=A.STATUS_CAME)),
                 revenue=Sum("price", filter=Q(status=A.STATUS_CAME)),
             ).order_by("start__date"))
    for r in drows:
        by_day.append({
            "date": r["start__date"],
            "total": r["total"],
            "came": r["came"],
            "revenue": int(r["revenue"] or 0),
        })

    return {
        "period": {"start": start, "end": end, "label": label, "key": key},
        "totals": totals,
        "by_status": by_status,
        "by_source": by_source,
        "by_master": by_master,
        "by_service": by_service,
        "by_day": by_day,
    }


def _detail_rows(start, end):
    """Построчная детализация всех записей за период (для листа «Детализация»)."""
    qs = (A.objects.filter(start__date__gte=start, start__date__lte=end)
          .select_related("client", "employee", "service")
          .order_by("start"))
    rows = []
    for a in qs:
        local = timezone.localtime(a.start)
        rows.append([
            local.strftime("%d.%m.%Y"),
            local.strftime("%H:%M"),
            str(a.client) if a.client_id else "",
            getattr(a.client, "phone", "") or "",
            a.employee.full_name if a.employee_id else "",
            a.service.name if a.service_id else "",
            STATUS_LABELS.get(a.status, a.status),
            SOURCE_LABELS.get(a.source, a.source),
            a.external_system or "",
            int(a.price or 0),
        ])
    return rows


# ============================================================================
# Выгрузка в Excel (.xlsx)
# ============================================================================
def to_xlsx(report):
    """Возвращает bytes готового .xlsx по данным build_report + детализацию."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="2F3A45")
    title_font = Font(bold=True, size=13)
    t = report["totals"]
    p = report["period"]

    wb = Workbook()

    def style_header(ws, ncols, row=1):
        for c in range(1, ncols + 1):
            cell = ws.cell(row=row, column=c)
            cell.font = head_font
            cell.fill = head_fill
            cell.alignment = Alignment(vertical="center")

    def autowidth(ws, widths):
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w

    # --- Лист: Сводка ---
    ws = wb.active
    ws.title = "Сводка"
    ws["A1"] = "Аналитика по записям"
    ws["A1"].font = title_font
    ws["A2"] = f"Период: {p['start']:%d.%m.%Y} — {p['end']:%d.%m.%Y}"
    summary = [
        ("Записей всего", t["total"]),
        ("Пришли", t["came"]),
        ("Ожидают / подтвердили", t["waiting"]),
        ("Не пришли", t["noshow"]),
        ("Доля неявок, %", t["noshow_rate"]),
        ("Выручка (пришедшие), ₽", t["revenue"]),
        ("Средний чек, ₽", t["avg_check"]),
        ("Онлайн-записи (портал + внешние)", t["online"]),
        ("Доля онлайн-записи, %", t["online_rate"]),
    ]
    r = 4
    for name, val in summary:
        ws.cell(row=r, column=1, value=name)
        ws.cell(row=r, column=2, value=val)
        r += 1
    autowidth(ws, [34, 18])

    # --- Лист: По статусам ---
    ws = wb.create_sheet("По статусам")
    ws.append(["Статус", "Записей", "Доля, %"])
    style_header(ws, 3)
    for row in report["by_status"]:
        ws.append([row["label"], row["count"], row["pct"]])
    autowidth(ws, [22, 12, 10])

    # --- Лист: По источникам ---
    ws = wb.create_sheet("По источникам")
    ws.append(["Источник", "Записей", "Доля, %", "Выручка, ₽"])
    style_header(ws, 4)
    for row in report["by_source"]:
        ws.append([row["label"], row["count"], row["pct"], row["revenue"]])
    autowidth(ws, [22, 12, 10, 14])

    # --- Лист: По мастерам ---
    ws = wb.create_sheet("По мастерам")
    ws.append(["Мастер", "Записей", "Пришли", "Не пришли", "Выручка, ₽"])
    style_header(ws, 5)
    for row in report["by_master"]:
        ws.append([row["name"], row["total"], row["came"], row["noshow"], row["revenue"]])
    autowidth(ws, [26, 12, 10, 12, 14])

    # --- Лист: По услугам ---
    ws = wb.create_sheet("По услугам")
    ws.append(["Услуга", "Записей", "Пришли", "Выручка, ₽"])
    style_header(ws, 4)
    for row in report["by_service"]:
        ws.append([row["name"], row["total"], row["came"], row["revenue"]])
    autowidth(ws, [30, 12, 10, 14])

    # --- Лист: По дням ---
    ws = wb.create_sheet("По дням")
    ws.append(["Дата", "Записей", "Пришли", "Выручка, ₽"])
    style_header(ws, 4)
    for row in report["by_day"]:
        ws.append([row["date"].strftime("%d.%m.%Y"), row["total"], row["came"], row["revenue"]])
    autowidth(ws, [14, 12, 10, 14])

    # --- Лист: Детализация ---
    ws = wb.create_sheet("Детализация")
    ws.append(["Дата", "Время", "Клиент", "Телефон", "Мастер", "Услуга",
               "Статус", "Источник", "Внешняя система", "Цена, ₽"])
    style_header(ws, 10)
    for row in _detail_rows(p["start"], p["end"]):
        ws.append(row)
    autowidth(ws, [12, 8, 22, 16, 18, 24, 14, 16, 16, 10])
    ws.freeze_panes = "A2"

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ============================================================================
# Финансовый срез (вкладка «Финансы» дашборда)
# ============================================================================
def build_finance(start, end, label="", key="", with_payments=False, with_payroll=False):
    """Финансы за период: выручка, чек, способы оплаты, ЗП как расход, чистыми.

    with_payments/with_payroll включают соответствующие блоки (по включённым
    модулям и правам — решает вызывающий код).
    """
    qs = A.objects.filter(start__date__gte=start, start__date__lte=end)
    came_qs = qs.filter(status=A.STATUS_CAME)
    came = came_qs.count()
    revenue = int(came_qs.aggregate(s=Sum("price"))["s"] or 0)
    avg_check = int(revenue / came) if came else 0

    # Способы оплаты (принятые платежи) + комиссия эквайринга
    acquiring = 0
    by_method = []
    if with_payments:
        from payments.models import Payment
        pq = Payment.objects.filter(
            status=Payment.PAID,
            created_at__date__gte=start, created_at__date__lte=end,
        )
        acquiring = int(pq.aggregate(s=Sum("acquiring_fee"))["s"] or 0)
        labels = dict(Payment.METHOD_CHOICES)
        for code, _lbl in Payment.METHOD_CHOICES:
            mq = pq.filter(method=code)
            cnt = mq.count()
            if cnt:
                by_method.append({
                    "label": labels[code], "count": cnt,
                    "amount": int(mq.aggregate(s=Sum("amount"))["s"] or 0),
                })

    # По мастерам: выручка (+ ЗП и остаток, если доступен расчёт ЗП)
    payroll_fund = 0
    by_master = []
    if with_payroll:
        from payroll.engine import compute
        from staff.models import Employee
        for e in Employee.objects.filter(is_active=True):
            r = compute(e, start, end)
            if r["revenue"] or r["total"]:
                by_master.append({
                    "name": e.full_name, "revenue": r["revenue"],
                    "payroll": r["total"], "margin": r["revenue"] - r["total"],
                })
                payroll_fund += r["total"]
        by_master.sort(key=lambda x: x["revenue"], reverse=True)
    else:
        for r in came_qs.values("employee__full_name").annotate(rev=Sum("price")):
            by_master.append({
                "name": r["employee__full_name"] or "—",
                "revenue": int(r["rev"] or 0), "payroll": None, "margin": None,
            })
        by_master.sort(key=lambda x: x["revenue"], reverse=True)

    # По услугам (выручка)
    by_service = []
    for r in came_qs.values("service__name").annotate(rev=Sum("price"), n=Count("id")):
        by_service.append({
            "name": r["service__name"] or "— без услуги —",
            "revenue": int(r["rev"] or 0), "count": r["n"],
        })
    by_service.sort(key=lambda x: x["revenue"], reverse=True)

    # По дням (выручка)
    by_day = []
    for r in came_qs.values("start__date").annotate(rev=Sum("price")).order_by("start__date"):
        by_day.append({"date": r["start__date"], "revenue": int(r["rev"] or 0)})

    net = revenue - acquiring - payroll_fund

    return {
        "period": {"start": start, "end": end, "label": label, "key": key},
        "totals": {
            "revenue": revenue, "came": came, "avg_check": avg_check,
            "acquiring": acquiring, "payroll_fund": payroll_fund, "net": net,
        },
        "with_payments": with_payments,
        "with_payroll": with_payroll,
        "by_method": by_method,
        "by_service": by_service,
        "by_master": by_master,
        "by_day": by_day,
    }


def to_xlsx_finance(report):
    """Выгрузка финансового среза в .xlsx."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="2F3A45")
    title_font = Font(bold=True, size=13)
    t = report["totals"]
    p = report["period"]

    wb = Workbook()

    def style_header(ws, ncols):
        for c in range(1, ncols + 1):
            cell = ws.cell(row=1, column=c)
            cell.font = head_font
            cell.fill = head_fill
            cell.alignment = Alignment(vertical="center")

    def autowidth(ws, widths):
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w

    ws = wb.active
    ws.title = "Сводка"
    ws["A1"] = "Финансы"
    ws["A1"].font = title_font
    ws["A2"] = f"Период: {p['start']:%d.%m.%Y} — {p['end']:%d.%m.%Y}"
    summary = [("Выручка (пришедшие), ₽", t["revenue"]),
               ("Визитов", t["came"]),
               ("Средний чек, ₽", t["avg_check"])]
    if report["with_payments"]:
        summary.append(("Комиссия эквайринга, ₽", t["acquiring"]))
    if report["with_payroll"]:
        summary.append(("Фонд ЗП, ₽", t["payroll_fund"]))
    if report["with_payments"] or report["with_payroll"]:
        summary.append(("Остаток (выручка − эквайринг − ЗП), ₽", t["net"]))
    r = 4
    for name, val in summary:
        ws.cell(row=r, column=1, value=name)
        ws.cell(row=r, column=2, value=val)
        r += 1
    autowidth(ws, [40, 18])

    if report["with_payments"]:
        ws = wb.create_sheet("Способы оплаты")
        ws.append(["Способ", "Операций", "Сумма, ₽"])
        style_header(ws, 3)
        for row in report["by_method"]:
            ws.append([row["label"], row["count"], row["amount"]])
        autowidth(ws, [22, 12, 14])

    ws = wb.create_sheet("По услугам")
    ws.append(["Услуга", "Визитов", "Выручка, ₽"])
    style_header(ws, 3)
    for row in report["by_service"]:
        ws.append([row["name"], row["count"], row["revenue"]])
    autowidth(ws, [30, 12, 14])

    ws = wb.create_sheet("По мастерам")
    if report["with_payroll"]:
        ws.append(["Мастер", "Выручка, ₽", "ЗП, ₽", "Остаток, ₽"])
        style_header(ws, 4)
        for row in report["by_master"]:
            ws.append([row["name"], row["revenue"], row["payroll"], row["margin"]])
        autowidth(ws, [26, 14, 14, 14])
    else:
        ws.append(["Мастер", "Выручка, ₽"])
        style_header(ws, 2)
        for row in report["by_master"]:
            ws.append([row["name"], row["revenue"]])
        autowidth(ws, [26, 14])

    ws = wb.create_sheet("По дням")
    ws.append(["Дата", "Выручка, ₽"])
    style_header(ws, 2)
    for row in report["by_day"]:
        ws.append([row["date"].strftime("%d.%m.%Y"), row["revenue"]])
    autowidth(ws, [14, 14])

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
