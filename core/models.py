"""
Базовые модели каркаса: Tenant, User, Role, AuditLog.

Это несущий слой. Клиентские (бизнес-) модели модулей будут наследоваться от
TenantModel (см. managers.py) и автоматически изолироваться по тенанту.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models

from core.managers import TenantModel
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
    # Оплачено до (ручная отметка провайдером; позже свяжем с авто-заморозкой)
    paid_until = models.DateField("Оплачено до", null=True, blank=True)
    # Комиссия эквайринга, % (при оплате картой — идёт в себестоимость/уменьшает нетто)
    acquiring_pct = models.DecimalField("Эквайринг, %", max_digits=5, decimal_places=2, default=0)

    # --- Кастомный домен (апселл). Поддомен *.BASE_DOMAIN работает и без этого. ---
    custom_domain = models.CharField(
        "Свой домен", max_length=255, null=True, blank=True, unique=True,
        help_text="Напр. rogaikopyta.ru — клиент направляет его CNAME на наш сервер",
    )
    custom_domain_verified = models.BooleanField("Домен подтверждён", default=False)
    # Токен для подтверждения владения доменом (DNS TXT), генерируется при задании домена
    domain_token = models.CharField("Токен проверки домена", max_length=64, blank=True)

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
    # Роль — только ПРЕСЕТ (заготовка галочек), с которого копируются права при
    # назначении. Реальные доступы хранятся на пользователе (permission_codes),
    # поэтому их можно точечно править в конкретном аккаунте.
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        related_name="users",
        null=True,
        blank=True,
        verbose_name="Роль (пресет)",
    )
    # Персональный набор КОДОВ прав этого аккаунта (deny-by-default). Копируется из
    # пресета роли при назначении, затем редактируется индивидуально.
    permission_codes = models.JSONField("Коды прав", default=list, blank=True)
    # Провайдерский админ: «одно кольцо» над всеми тенантами.
    is_provider_admin = models.BooleanField("Провайдерский админ", default=False)
    # Двухфакторная аутентификация (TOTP). secret — base32; codes — хэши резервных кодов.
    totp_secret = models.CharField("TOTP-секрет", max_length=64, blank=True)
    totp_enabled = models.BooleanField("2FA включена", default=False)
    backup_codes = models.JSONField("Резервные коды (хэши)", default=list, blank=True)
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


# --- История действий салона (с возможностью отмены) ---
class ActivityLog(TenantModel):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ACTION_CHOICES = [(CREATE, "Создание"), (UPDATE, "Изменение"), (DELETE, "Удаление")]

    actor = models.ForeignKey(
        "core.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="activity",
    )
    action = models.CharField("Действие", max_length=10, choices=ACTION_CHOICES)
    model_label = models.CharField("Модель", max_length=100)       # напр. appointments.Appointment
    object_pk = models.CharField("ID объекта", max_length=50)
    object_repr = models.CharField("Объект", max_length=250)       # имя на момент действия
    # Снимок состояния «до» (JSON сериализатора Django) — для отката
    before_json = models.TextField("Снимок до", blank=True)
    created_at = models.DateTimeField("Когда", auto_now_add=True, db_index=True)
    undone = models.BooleanField("Отменено", default=False)
    undone_at = models.DateTimeField("Отменено в", null=True, blank=True)
    undone_by = models.ForeignKey(
        "core.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="undos",
    )

    class Meta:
        verbose_name = "Запись истории"
        verbose_name_plural = "История действий"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_display()} · {self.object_repr}"
