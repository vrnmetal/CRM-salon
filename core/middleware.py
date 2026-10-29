"""
TenantMiddleware — определяет текущего тенанта на каждый запрос и кладёт его
(вместе с пользователем) в threadlocal, чтобы TenantManager автоматически
фильтровал данные по тенанту.

Порядок резолва:
  1) по поддомену (salon1.<BASE_DOMAIN>) — канонический способ;
  2) иначе — по тенанту залогиненного пользователя.
Провайдерский админ может не иметь тенанта (tenant=None) — это нормально.
"""
from django.conf import settings

from core import tenancy


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Кладём пользователя в контекст (для аудита: кто совершает действие)
        user = getattr(request, "user", None)
        tenancy.set_current_user(user if getattr(user, "is_authenticated", False) else None)

        # Резолвим тенанта и прикрепляем к запросу + в threadlocal
        tenant = self._resolve_tenant(request, user)
        request.tenant = tenant
        tenancy.set_current_tenant(tenant)

        try:
            response = self.get_response(request)
        finally:
            # Чистим контекст, чтобы ничего не «протекло» между запросами
            tenancy.clear()
        return response

    def _resolve_tenant(self, request, user):
        # Импорт внутри метода — модель может быть не готова на уровне модуля
        from core.models import Tenant

        # 1) По поддомену
        slug = self._subdomain(request)
        if slug:
            tenant = Tenant.objects.filter(slug=slug).first()
            if tenant is not None:
                return tenant

        # 2) По пользователю
        if getattr(user, "is_authenticated", False) and getattr(user, "tenant_id", None):
            return user.tenant

        return None

    @staticmethod
    def _subdomain(request):
        # Вытаскиваем первую метку хоста, если это поддомен BASE_DOMAIN
        host = request.get_host().split(":")[0]
        base = settings.BASE_DOMAIN
        if host == base or not host.endswith("." + base):
            return None
        label = host[: -(len(base) + 1)]
        # "www" и пустое — не тенанты
        if not label or label == "www":
            return None
        # Берём последнюю метку перед базовым доменом (salon1.app.local -> salon1)
        return label.split(".")[-1]
