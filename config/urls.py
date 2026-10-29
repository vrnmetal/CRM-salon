"""
Корневой URLconf.

Отличие от ремонтной CRM (там все url были прямо здесь без include): здесь
проект МОДУЛЬНЫЙ, поэтому каждый модуль приносит свой urls.py, а реестр модулей
подключает только те, что реально существуют. Так модуль можно включать/выключать,
не трогая корневой файл. core подключён всегда (это ядро).
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core.modules import iter_module_urlconfs

urlpatterns = [
    path("django-admin/", admin.site.urls),
    # Ядро: вход, домашний роутер по роли, настройки доступа
    path("", include("core.urls")),
]

# Подключаем urls.py каждого зарегистрированного модуля, у которого он есть.
# Доступность модуля КОНКРЕТНОМУ тенанту проверяется отдельно (флаги + права),
# здесь только монтируем маршруты в проект.
for prefix, urlconf in iter_module_urlconfs():
    urlpatterns.append(path(prefix, include(urlconf)))

# Отдача медиа (логотипы) при локальной разработке
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
