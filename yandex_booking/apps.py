from django.apps import AppConfig


class YandexBookingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "yandex_booking"
    verbose_name = "Онлайн-запись в Яндекс.Картах"

    def ready(self):
        # Подключаем сигналы обратной синхронизации (изменения записи → Яндекс)
        from yandex_booking import signals  # noqa: F401
