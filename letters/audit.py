"""Write AuditEvent rows. Never raises: an audit failure must not break the request."""
import logging

from django.conf import settings

from .models import AuditEvent

log = logging.getLogger(__name__)


def client_ip(request) -> str | None:
    if request is None:
        return None
    if getattr(settings, "MAPINC_BEHIND_PROXY", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()[:45]
    return request.META.get("REMOTE_ADDR") or None


def record(request, action: str, *, case_encounter: str = "", detail: str = "", windows_user: str = ""):
    user = ""
    if request is not None:
        auth_user = getattr(request, "user", None)
        if auth_user is not None and auth_user.is_authenticated:
            user = auth_user.get_username()
    try:
        return AuditEvent.objects.create(
            user=user[:150], windows_user=(windows_user or "")[:150], ip=client_ip(request),
            action=action, case_encounter=(case_encounter or "")[:100], detail=(detail or "")[:500])
    except Exception:  # noqa: BLE001
        log.exception("Could not write audit event %s", action)
        return None
