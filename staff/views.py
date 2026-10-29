"""Сотрудники: список и добавление из интерфейса (не только через админку)."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render

from core.permissions import has_perm, requires
from staff.models import Employee


@login_required
@requires("staff.view")
def staff_list(request):
    if request.method == "POST":
        # Создание сотрудника — отдельное право
        if not has_perm(request.user, "staff.create"):
            raise PermissionDenied("Нет права: staff.create")
        name = (request.POST.get("full_name") or "").strip()
        if name:
            Employee.objects.create(
                full_name=name,
                specialization=(request.POST.get("specialization") or "").strip(),
                color=(request.POST.get("color") or "#0071E3").strip(),
            )
        return redirect("staff_list")

    employees = Employee.objects.all()
    return render(request, "staff/list.html", {"employees": employees})
