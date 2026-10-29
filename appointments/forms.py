"""
Формы записей: быстрая запись и полное редактирование.

Редактирование повторяет логику карточки записи: клиент (подтягивается из базы),
мастер, несколько услуг, дата/время, статус, итоговая цена (можно скидку).
"""
from django import forms

from appointments.models import Appointment, Service
from staff.models import Employee


class QuickAppointmentForm(forms.Form):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.none(), label="Мастер", empty_label="Выберите мастера"
    )
    service = forms.ModelChoiceField(
        queryset=Service.objects.none(), label="Услуга", empty_label="Выберите услугу"
    )
    date = forms.DateField(label="Дата", widget=forms.DateInput(attrs={"type": "date"}))
    time = forms.TimeField(label="Время", widget=forms.TimeInput(attrs={"type": "time"}))
    client_phone = forms.CharField(label="Телефон клиента", max_length=32)
    client_name = forms.CharField(label="Имя клиента", max_length=150, required=False)
    pdn_consent = forms.BooleanField(label="Клиент дал согласие на обработку ПДн", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(is_active=True)
        self.fields["service"].queryset = Service.objects.filter(is_active=True)


# Сколько услуг можно выбрать в одной записи (в редактировании)
MAX_SERVICES = 4


class EditAppointmentForm(forms.Form):
    client_phone = forms.CharField(label="Телефон клиента", max_length=32)
    client_name = forms.CharField(label="Имя клиента", max_length=150, required=False)
    employee = forms.ModelChoiceField(queryset=Employee.objects.none(), label="Мастер")
    date = forms.DateField(label="Дата", widget=forms.DateInput(attrs={"type": "date"}))
    time = forms.TimeField(label="Время", widget=forms.TimeInput(attrs={"type": "time"}))
    status = forms.ChoiceField(label="Статус", choices=Appointment.STATUS_CHOICES)
    # Итоговая сумма (можно уменьшить — скидка). Пусто → пересчитается из услуг.
    price = forms.DecimalField(label="К оплате, ₽", max_digits=10, decimal_places=2, required=False)
    comment = forms.CharField(label="Комментарий", max_length=500, required=False,
                              widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active = Employee.objects.filter(is_active=True)
        self.fields["employee"].queryset = active
        services = Service.objects.filter(is_active=True)
        # Несколько услуг: первая обязательна, остальные — опционально
        for i in range(1, MAX_SERVICES + 1):
            self.fields[f"service_{i}"] = forms.ModelChoiceField(
                queryset=services, required=(i == 1), empty_label="—",
                label="Услуга" if i == 1 else f"Ещё услуга",
            )

    def chosen_services(self):
        # Выбранные услуги по порядку (без пустых)
        result = []
        for i in range(1, MAX_SERVICES + 1):
            s = self.cleaned_data.get(f"service_{i}")
            if s:
                result.append(s)
        return result
