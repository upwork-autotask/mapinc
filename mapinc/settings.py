"""
Django settings for mapinc. All environment-specific values come from
mapinc.ini next to manage.py (see mapinc.ini.example).
"""
import configparser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_INI_PATH = BASE_DIR / "mapinc.ini"
if not _INI_PATH.exists():
    raise RuntimeError(
        f"Missing {_INI_PATH}. Copy mapinc.ini.example to mapinc.ini and edit it."
    )
MAPINC_CONFIG = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
MAPINC_CONFIG.read(_INI_PATH, encoding="utf-8")

_db = MAPINC_CONFIG["database"]
_app = MAPINC_CONFIG["app"]

SECRET_KEY = _app.get("secret_key", "change-me")
DEBUG = _app.getboolean("debug", fallback=False)
ALLOWED_HOSTS = [h.strip() for h in _app.get("allowed_hosts", "*").split(",") if h.strip()]

PDF_CONVERTER = _app.get("pdf_converter", "word").strip().lower()
WORD_TIMEOUT_SECONDS = _app.getint("word_timeout_seconds", fallback=60)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "letters",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "mapinc.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "mapinc.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _db.get("name", "mapinc"),
        "USER": _db.get("user", "mapinc"),
        "PASSWORD": _db.get("password", ""),
        "HOST": _db.get("host", "localhost"),
        "PORT": _db.get("port", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/New_York"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
