from django.apps import AppConfig


class StockConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "stock"
    verbose_name = "Склад и тех. карты"

    def ready(self):
        # Подключаем авто-списание расходников при проведении визита
        from stock import signals  # noqa: F401
