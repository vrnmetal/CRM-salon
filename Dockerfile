# Образ приложения. Код КОПИРУЕТСЯ в образ (в проде не монтируется томом),
# поэтому любое изменение кода на проде = пересборка образа.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Системные зависимости (psycopg собранному из binary обычно хватает, libpq на всякий)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Сначала зависимости (кэш слоёв), потом код
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# По умолчанию — gunicorn (прод). Локально docker-compose переопределяет на runserver.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
