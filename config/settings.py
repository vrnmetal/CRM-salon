"""
Настройки проекта.

Читаем конфигурацию из переменных окружения (.env разворачивается в окружение
через docker compose или вручную). ВАЖНО: в .env не должно быть пробелов после `=`.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


# --- Авто-загрузка .env (без внешних зависимостей) ---
# manage.py на хосте сам не читает .env (его читает только docker compose),
# поэтому подхватываем файл здесь: переменные, уже заданные в окружении, не трогаем.
def _load_dotenv(path: Path):
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        # Пропускаем пустые строки и комментарии
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        # Явное окружение приоритетнее файла
        if key and key not in os.environ:
            os.environ[key] = value.strip()


_load_dotenv(BASE_DIR / ".env")


# --- Вспомогательная функция чтения булевых флагов из окружения ---
def env_bool(name: str, default: bool = False) -> bool:
    # Переменная окружения -> True только для явных "1/true/yes/on"
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# --- Базовые флаги ---
# Секрет берём из окружения; дефолт только для локального dev (в проде обязателен свой)
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")
DEBUG = env_bool("DEBUG", True)

# USE_HTTPS — ОТДЕЛЬНЫЙ флаг, НЕ завязан на DEBUG.
# Если True — включаем secure-куки. На http это рвёт логин, поэтому локально False.
USE_HTTPS = env_bool("USE_HTTPS", False)

# Хосты и доверенные origin для CSRF (список через запятую в окружении)
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "*").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

# Базовый домен, на поддоменах которого живут тенанты (salon1.<BASE_DOMAIN>)
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "localhost")


# --- Приложения ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Наш каркас
    "core",
    # Бизнес-модули
    "staff",
    "clients",
    "appointments",
]


# --- Middleware ---
# TenantMiddleware ставим ПОСЛЕ аутентификации: ему нужен request.user,
# и он кладёт текущего тенанта/пользователя в threadlocal для TenantManager.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.TenantMiddleware",
]

ROOT_URLCONF = "config.urls"

# --- Шаблоны ---
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Наши процессоры: брендинг тенанта, подсказки, меню модулей
                "core.context_processors.branding",
                "core.context_processors.ui_flags",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- База данных ---
# По умолчанию PostgreSQL (docker compose поднимает db). Для быстрого локального
# запуска без Docker можно выставить DB_ENGINE=sqlite.
if os.environ.get("DB_ENGINE", "postgres").strip().lower() == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "salon"),
            "USER": os.environ.get("DB_USER", "salon"),
            "PASSWORD": os.environ.get("DB_PASSWORD", "salon"),
            "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
            # 5433 по умолчанию, чтобы не конфликтовать с ремонтной CRM (5432)
            "PORT": os.environ.get("DB_PORT", "5433"),
        }
    }


# --- Кастомная модель пользователя (с тенантом и ролью) ---
AUTH_USER_MODEL = "core.User"

# Куда редиректить после входа/выхода
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"


# --- Пароли ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Локализация ---
LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True


# --- Статика и медиа ---
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Secure-куки только при USE_HTTPS ---
# Разделение флага спасает логин по http локально (secure-кука иначе не отправится).
if USE_HTTPS:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
