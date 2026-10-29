"""
Контекст текущего тенанта и пользователя на время обработки запроса.

Храним в threadlocal: middleware кладёт сюда тенанта/пользователя из request,
а TenantManager читает отсюда, чтобы автоматически фильтровать queryset по тенанту.
Так изоляция данных работает ВЕЗДЕ по умолчанию, а не вручную в каждой вьюхе.
"""
import threading
from contextlib import contextmanager

_state = threading.local()


# --- Текущий тенант ---
def set_current_tenant(tenant):
    _state.tenant = tenant


def get_current_tenant():
    return getattr(_state, "tenant", None)


# --- Текущий пользователь (для аудита: кто совершил действие) ---
def set_current_user(user):
    _state.user = user


def get_current_user():
    return getattr(_state, "user", None)


# --- Сброс контекста (на всякий случай между запросами/в тестах) ---
def clear():
    _state.tenant = None
    _state.user = None


@contextmanager
def tenant_context(tenant):
    """Временно выполнить блок в контексте указанного тенанта (фон/скрипты/тесты)."""
    previous = get_current_tenant()
    set_current_tenant(tenant)
    try:
        yield
    finally:
        set_current_tenant(previous)
