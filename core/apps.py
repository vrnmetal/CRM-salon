from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Ядро"

    def ready(self):
        # При старте подтягиваем реестры прав/подсказок/модулей ядра,
        # чтобы они зарегистрировались (импорт = регистрация).
        from core import permissions  # noqa: F401
        from core import hints  # noqa: F401
        from core import modules  # noqa: F401
