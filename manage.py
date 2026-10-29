#!/usr/bin/env python
"""Точка входа Django для управления проектом (runserver, migrate и т.д.)."""
import os
import sys


def main():
    # Указываем модуль настроек по умолчанию
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Не удалось импортировать Django. Активировано ли окружение .venv?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
