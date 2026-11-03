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
        user = getattr(request, "user", None)

        # --- Impersonation: провайдер «вошёл как» салон (с аудитом) ---
        # В сессии лежит id провайдера и id пользователя-владельца салона.
        request.impersonator = None
        imp_user_id = request.session.get("impersonate_user_id") if hasattr(request, "session") else None
        if imp_user_id and getattr(user, "is_provider_admin", False):
            from core.models import User as U
            target = U.objects.filter(pk=imp_user_id, is_provider_admin=False).first()
            if target is not None:
                request.impersonator = user      # помним, кто на самом деле вошёл
                request.user = target            # дальше система видит владельца салона
                user = target

        # Кладём пользователя в контекст (для аудита: кто совершает действие)
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

        host = request.get_host().split(":")[0]

        # 1) По поддомену *.BASE_DOMAIN
        slug = self._subdomain(request)
        if slug:
            tenant = Tenant.objects.filter(slug=slug).first()
            if tenant is not None:
                return tenant

        # 2) По кастомному домену клиента (rogaikopyta.ru) — только подтверждённому
        tenant = Tenant.objects.filter(custom_domain=host, custom_domain_verified=True).first()
        if tenant is not None:
            return tenant

        # 3) По пользователю (в т.ч. при impersonation — владелец салона)
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
