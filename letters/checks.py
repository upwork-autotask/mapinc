"""
Startup checks that refuse an unsafe configuration when [app] production = true.
Run by `manage.py check`, `migrate`, `runserver` and run.bat.
"""
from django.conf import settings
from django.core.checks import Error, Tags, register

SAFE_SSLMODES = {"require", "verify-ca", "verify-full"}
DEV_DB_USERS = {"mapinc", "postgres"}


@register(Tags.security)
def production_config(app_configs, **kwargs):
    if not getattr(settings, "MAPINC_PRODUCTION", False):
        return []
    errors = []
    db = settings.DATABASES["default"]
    if settings.DEBUG:
        errors.append(Error("debug must be false in production.", id="letters.E001"))
    if settings.SECRET_KEY.startswith("change-me") or len(settings.SECRET_KEY) < 32:
        errors.append(Error("secret_key must be a long random string (32+ characters).",
                            hint="python -c \"import secrets; print(secrets.token_urlsafe(48))\"", id="letters.E002"))
    if "*" in settings.ALLOWED_HOSTS or not settings.ALLOWED_HOSTS:
        errors.append(Error("allowed_hosts must list the server's host name(s), not *.", id="letters.E003"))
    if db.get("OPTIONS", {}).get("sslmode") not in SAFE_SSLMODES:
        errors.append(Error("[database] sslmode must be require, verify-ca or verify-full.", id="letters.E004"))
    if db.get("USER") in DEV_DB_USERS:
        errors.append(Error(f"[database] user {db.get('USER')!r} is a development/superuser role; "
                            "use the least-privilege mapinc_app role.", id="letters.E005"))
    if getattr(settings, "MAPINC_AUTH_MODE", "open") == "open":
        errors.append(Error("auth_mode must be login or remote_user in production.", id="letters.E006"))
    if not getattr(settings, "MAPINC_HTTPS", False):
        errors.append(Error("https must be true in production (put IIS/TLS in front, see docs).", id="letters.E007"))
    if getattr(settings, "MAPINC_ALLOW_QUERY_PREFILL", False):
        errors.append(Error("allow_query_prefill must be false in production (keeps PHI out of URLs).",
                            id="letters.E008"))
    return errors
