"""
Базовые модели каркаса: Tenant, User, Role, AuditLog.

Это несущий слой. Клиентские (бизнес-) модели модулей будут наследоваться от
TenantModel (см. managers.py) и автоматически изолироваться по тенанту.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models

from core.modules import CORE_MODULE_CODES


# --- Тенант: один изолированный бизнес (салон) внутри общей системы ---
class Tenant(models.Model):
    # Отображаемое имя бизнеса
    name = models.CharField("Название", max_length=200)
    # Поддомен: salon1.<BASE_DOMAIN>. Уникален, по нему резолвим тенанта.
    slug = models.SlugField("Поддомен", max_length=63, unique=True)
    # Рубильник доступа: не заплатил/заморожен — выключаем, данные не трогаем.
    is_active = models.BooleanField("Активен", default=True)

    # --- Модульная сборка: какие НЕ-ядровые модули включены этому тенанту ---
    # Ядровые модули включены всегда (см. is_module_enabled в modules.py).
    enabled_modules = models.JSONField("Включённые модули", default=list, blank=True)

    # --- White-label (брендирование) ---
    brand_name = models.CharField("Бренд", max_length=200, blank=True)
    logo = models.ImageField("Логотип", upload_to="logos/", blank=True, null=True)
    # Акцентный цвет тенанта (hex). Подменяет --accent поверх общего app.css.
    accent_color = models.CharField("Акцент (hex)", max_length=7, blank=True)
    # Имя пресета темы (нейтральная база фиксирована, выбирается только акцент/пресет)
    theme_preset = models.CharField("Пресет темы", max_length=50, blank=True)
    # Пресет шрифта (нейтральная база — системный SF; можно выбрать из безопасного набора)
    font_preset = models.CharField("Шрифт", max_length=20, blank=True)

    # Тариф (для биллинга позже; пока справочно)
    plan = models.CharField("Тариф", max_length=50, blank=True)

    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Тенант"
        verbose_name_plural = "Тенанты"

    def __str__(self):
        return self.name

    def is_module_on(self, code: str) -> bool:
        # Ядровые модули всегда включены; остальные — по списку enabled_modules.
        if code in CORE_MODULE_CODES:
            return True
        return code in (self.enabled_modules or [])


# --- Роль: пресет-набор прав внутри тенанта (собственник/админ/мастер) ---
class Role(models.Model):
    # Роль принадлежит тенанту (у каждого бизнеса свои роли, засеянные из пресетов)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="roles", verbose_name="Тенант"
    )
    name = models.CharField("Название", max_length=100)
    # Технический код пресета, из которого засеяна роль (owner/admin/master)
    preset_code = models.CharField("Код пресета", max_length=50, blank=True)
    # Набор КОДОВ прав (строки из реестра permissions.py). deny-by-default:
    # право есть только если его код здесь присутствует.
    permission_codes = models.JSONField("Коды прав", default=list, blank=True)

    class Meta:
        verbose_name = "Роль"
        verbose_name_plural = "Роли"
        unique_together = [("tenant", "name")]

    def __str__(self):
        return f"{self.name} ({self.tenant.slug})"


# --- Пользователь: сотрудник тенанта ИЛИ провайдерский админ (tenant=null) ---
class User(AbstractUser):
    # К какому тенанту относится сотрудник. null = провайдерский уровень.
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True,
        verbose_name="Тенант",
    )
    # Роль внутри тенанта (определяет набор прав)
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        related_name="users",
        null=True,
        blank=True,
        verbose_name="Роль",
    )
    # Провайдерский админ: «одно кольцо» над всеми тенантами. Требует 2FA (позже).
    is_provider_admin = models.BooleanField("Провайдерский админ", default=False)
    # Тумблер подсказок на уровне пользователя (новичок — вкл, профи — выкл).
    show_hints = models.BooleanField("Показывать подсказки", default=True)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"


# --- Аудит-лог: НЕИЗМЕНЯЕМАЯ лента действий (append-only, не обновляем/не удаляем) ---
class AuditLog(models.Model):
    tenant = models.ForeignKey(
        Tenant, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit"
    )
    user = models.ForeignKey(
        "core.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="audit"
    )
    # Тип действия, например "login", "impersonate.start", "appointment.create"
    action = models.CharField("Действие", max_length=100)
    # На что направлено действие (id/описание цели)
    target = models.CharField("Цель", max_length=200, blank=True)
    # Произвольные детали
    meta = models.JSONField("Детали", default=dict, blank=True)
    created_at = models.DateTimeField("Когда", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Запись аудита"
        verbose_name_plural = "Аудит"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action}"
