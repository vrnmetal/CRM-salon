"""
Проверка покрытия прав (запускать перед выдачей патча, как ast-проверку urls.py).

Идёт по всем маршрутам проекта и проверяет, что у каждой вьюхи, помеченной
@requires(code), этот код реально есть в реестре прав. Ловит опечатки и забытые
регистрации до того, как они доедут до прода.

Запуск:  python scripts/check_permissions.py
"""
import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DB_ENGINE", "sqlite")
os.environ.setdefault("SECRET_KEY", "check")
django.setup()

from django.urls import get_resolver  # noqa: E402

from core.permissions import REGISTRY  # noqa: E402


def iter_views(resolver, prefix=""):
    for pattern in resolver.url_patterns:
        if hasattr(pattern, "url_patterns"):
            yield from iter_views(pattern, prefix + str(pattern.pattern))
        else:
            yield prefix + str(pattern.pattern), pattern.callback


def main():
    problems = []
    checked = 0
    for route, callback in iter_views(get_resolver()):
        code = getattr(callback, "_required_permission", None)
        if code is None:
            continue
        checked += 1
        if code not in REGISTRY:
            problems.append(f"  {route}: право '{code}' НЕ в реестре")

    if problems:
        print("ПРОБЛЕМЫ С ПРАВАМИ:")
        print("\n".join(problems))
        sys.exit(1)
    print(f"OK: проверено защищённых вьюх — {checked}, все права в реестре.")


if __name__ == "__main__":
    main()
