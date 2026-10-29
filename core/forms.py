"""Формы раздела настроек: создание аккаунта и брендирование."""
from django import forms

from core.branding import font_choices
from core.models import Role, User


# --- Создание аккаунта сотрудника ---
class AccountCreateForm(forms.Form):
    username = forms.CharField(label="Логин", max_length=150)
    full_name = forms.CharField(label="Имя", max_length=150, required=False)
    role = forms.ModelChoiceField(queryset=Role.objects.none(), label="Роль")
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput, min_length=6)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        # Роли — только текущего тенанта (Role не тенант-менеджер, фильтруем явно)
        if tenant is not None:
            self.fields["role"].queryset = Role.objects.filter(tenant=tenant)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        # Логин уникален глобально (ограничение AbstractUser)
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Такой логин уже занят.")
        return username


# --- Брендирование: имя, акцент, логотип, шрифт ---
class BrandingForm(forms.Form):
    brand_name = forms.CharField(label="Название бренда", max_length=200, required=False)
    accent_color = forms.CharField(
        label="Акцентный цвет", required=False,
        widget=forms.TextInput(attrs={"type": "color"}),
    )
    font_preset = forms.ChoiceField(label="Шрифт", required=False, choices=font_choices)
    logo = forms.ImageField(label="Логотип", required=False)
    remove_logo = forms.BooleanField(label="Удалить логотип", required=False)
