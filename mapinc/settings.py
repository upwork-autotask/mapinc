"""
Django settings for mapinc. All environment-specific values come from
mapinc.ini next to manage.py (see mapinc.ini.example). Set the MAPINC_INI
environment variable to point at a different file (e.g. one with the
migration role for `manage.py migrate`).
"""
import configparser
import os
import sys
from datetime import timedelta
from pathlib import Path

if sys.version_info < (3, 10):
    raise SystemExit(
        "mapinc requires Python 3.10 or newer (3.13 recommended); this is Python "
        + sys.version.split()[0] + ".\n"
        "Recreate the virtualenv with a newer interpreter:\n"
        "    py -0                      (lists installed versions)\n"
        "    py -3.13 -m venv .venv\n"
        "    .\\.venv\\Scripts\\Activate.ps1\n"
        "    pip install -r requirements.txt"
    )

BASE_DIR = Path(__file__).resolve().parent.parent

_INI_PATH = Path(os.environ.get("MAPINC_INI") or BASE_DIR / "mapinc.ini")
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

# --- HIPAA hardening switches (see docs/hipaa-hardening-plan.md) -------------
MAPINC_PRODUCTION = _app.getboolean("production", fallback=False)
MAPINC_HTTPS = _app.getboolean("https", fallback=MAPINC_PRODUCTION)
MAPINC_BEHIND_PROXY = _app.getboolean("behind_proxy", fallback=False)
MAPINC_AUTH_MODE = _app.get("auth_mode", "open").strip().lower()          # open | login | remote_user
MAPINC_SESSION_MINUTES = _app.getint("session_minutes", fallback=30)
MAPINC_ALLOW_QUERY_PREFILL = _app.getboolean("allow_query_prefill", fallback=not MAPINC_PRODUCTION)
MAPINC_HANDOFF_MINUTES = _app.getint("handoff_minutes", fallback=5)
MAPINC_HANDOFF_ALLOWED_NETWORKS = [
    n.strip() for n in _app.get("handoff_allowed_networks", "").split(",") if n.strip()
]
if MAPINC_AUTH_MODE not in {"open", "login", "remote_user"}:
    raise RuntimeError(f"mapinc.ini: auth_mode must be open, login or remote_user (got {MAPINC_AUTH_MODE!r})")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",
    "letters",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "letters.middleware.NoStoreMiddleware",
    "axes.middleware.AxesMiddleware",
]
if MAPINC_AUTH_MODE == "remote_user":
    # IIS (Windows Authentication) forwards the logged-on user in X-Remote-User.
    MIDDLEWARE.insert(
        MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1,
        "letters.middleware.WindowsUserMiddleware",
    )

# AxesStandaloneBackend must come first: it blocks locked-out accounts before any real backend runs.
AUTHENTICATION_BACKENDS = ["axes.backends.AxesStandaloneBackend", "django.contrib.auth.backends.ModelBackend"]
if MAPINC_AUTH_MODE == "remote_user":
    AUTHENTICATION_BACKENDS.insert(1, "letters.auth.WindowsUserBackend")

ROOT_URLCONF = "mapinc.urls"

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
                "letters.context_processors.mapinc",
            ],
        },
    },
]

WSGI_APPLICATION = "mapinc.wsgi.application"

_db_options = {"sslmode": _db.get("sslmode", "prefer").strip()}
if _db.get("sslrootcert", "").strip():
    _db_options["sslrootcert"] = _db.get("sslrootcert").strip()

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _db.get("name", "mapinc"),
        "USER": _db.get("user", "mapinc"),
        "PASSWORD": _db.get("password", ""),
        "HOST": _db.get("host", "localhost"),
        "PORT": _db.get("port", "5432"),
        "OPTIONS": _db_options,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Login lockout (django-axes) ---------------------------------------------
AXES_FAILURE_LIMIT = _app.getint("lockout_failures", fallback=5)
AXES_COOLOFF_TIME = timedelta(minutes=_app.getint("lockout_minutes", fallback=15))
AXES_LOCKOUT_PARAMETERS = ["username"]                # lock the account, whatever the source address
# W006 warns that username-only lockout can be bypassed by rotating IPs; here it is deliberate so
# that one bad actor behind the shared office NAT cannot lock out every user at once.
SILENCED_SYSTEM_CHECKS = ["axes.W006"]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "letters/locked_out.html"
AXES_ENABLE_ACCESS_FAILURE_LOG = True

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/New_York"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "settings"
LOGOUT_REDIRECT_URL = "letter_form"

# Serve /static/ from the app's static dirs without a collectstatic step (tiny LAN app).
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True

# --- Session / transport hardening -------------------------------------------
SESSION_COOKIE_AGE = MAPINC_SESSION_MINUTES * 60      # automatic logoff after inactivity
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True                     # idle timer, not absolute
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
if MAPINC_HTTPS:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
if MAPINC_BEHIND_PROXY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
