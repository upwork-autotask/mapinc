"""
Django settings for mapinc. Every environment-specific value is a MAPINC_*
environment variable; a .env file next to manage.py is read as a convenience
(see .env.example and mapinc/env.py).
"""
import sys
from datetime import timedelta
from pathlib import Path

from . import env

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

SECRET_KEY = env.get("MAPINC_SECRET_KEY", "change-me")
DEBUG = env.get_bool("MAPINC_DEBUG", False)
ALLOWED_HOSTS = env.get_list("MAPINC_ALLOWED_HOSTS", "*")

PDF_CONVERTER = env.get("MAPINC_PDF_CONVERTER", "word").lower()
WORD_TIMEOUT_SECONDS = env.get_int("MAPINC_WORD_TIMEOUT_SECONDS", 60)

# --- HIPAA hardening switches (see docs/hipaa-hardening-plan.md) -------------
MAPINC_PRODUCTION = env.get_bool("MAPINC_PRODUCTION", False)
MAPINC_HTTPS = env.get_bool("MAPINC_HTTPS", MAPINC_PRODUCTION)
MAPINC_BEHIND_PROXY = env.get_bool("MAPINC_BEHIND_PROXY", False)
MAPINC_AUTH_MODE = env.get("MAPINC_AUTH_MODE", "open").lower()          # open | login | remote_user
MAPINC_SESSION_MINUTES = env.get_int("MAPINC_SESSION_MINUTES", 30)
MAPINC_ALLOW_QUERY_PREFILL = env.get_bool("MAPINC_ALLOW_QUERY_PREFILL", not MAPINC_PRODUCTION)
MAPINC_HANDOFF_MINUTES = env.get_int("MAPINC_HANDOFF_MINUTES", 5)
MAPINC_HANDOFF_ALLOWED_NETWORKS = env.get_list("MAPINC_HANDOFF_ALLOWED_NETWORKS")
# Empty = any full path the launcher supplies; set it to limit where letters may be written.
MAPINC_ALLOWED_FOLDER_ROOTS = env.get_list("MAPINC_ALLOWED_FOLDER_ROOTS")
# "Open folder": the server may open Explorer, but only for a browser on the server itself.
MAPINC_LOCAL_EXPLORER = env.get_bool("MAPINC_LOCAL_EXPLORER", True)
# Optional URL scheme registered on staff PCs (deploy/open-folder) so remote browsers
# can open the folder too; empty means only the clipboard fallback is used.
MAPINC_FOLDER_PROTOCOL = env.get("MAPINC_FOLDER_PROTOCOL", "")
if MAPINC_AUTH_MODE not in {"open", "login", "remote_user"}:
    raise RuntimeError(f"MAPINC_AUTH_MODE must be open, login or remote_user (got {MAPINC_AUTH_MODE!r})")

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

_db_options = {"sslmode": env.get("MAPINC_DB_SSLMODE", "prefer")}
if env.get("MAPINC_DB_SSLROOTCERT"):
    _db_options["sslrootcert"] = env.get("MAPINC_DB_SSLROOTCERT")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env.get("MAPINC_DB_NAME", "mapinc"),
        "USER": env.get("MAPINC_DB_USER", "mapinc"),
        "PASSWORD": env.get("MAPINC_DB_PASSWORD", ""),
        "HOST": env.get("MAPINC_DB_HOST", "localhost"),
        "PORT": env.get("MAPINC_DB_PORT", "5432"),
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
AXES_FAILURE_LIMIT = env.get_int("MAPINC_LOCKOUT_FAILURES", 5)
AXES_COOLOFF_TIME = timedelta(minutes=env.get_int("MAPINC_LOCKOUT_MINUTES", 15))
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
