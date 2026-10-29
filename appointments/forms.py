"""
Форма быстрой записи. Минимум полей: кто (мастер), на что (услуга), когда
(дата+время) + клиент (телефон/имя). Длительность и цена берутся из услуги.
"""
from django import forms

from appointments.models import Service
from staff.models import Employee


class QuickAppointmentForm(forms.Form):
    # Querysets — тенант-ограниченные (контекст тенанта активен во время запроса)
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
        # Наполняем выпадающие списки активными мастерами/услугами текущего тенанта
        self.fields["employee"].queryset = Employee.objects.filter(is_active=True)
        self.fields["service"].queryset = Service.objects.filter(is_active=True)
