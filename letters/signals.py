from axes.signals import user_locked_out
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from . import audit
from .models import AuditEvent


@receiver(user_logged_in)
def _on_login(sender, request, user, **kwargs):
    audit.record(request, AuditEvent.Action.LOGIN)


@receiver(user_logged_out)
def _on_logout(sender, request, user, **kwargs):
    event = audit.record(request, AuditEvent.Action.LOGOUT)
    if event is not None and user is not None and not event.user:
        event.user = user.get_username()
        event.save(update_fields=["user"])


@receiver(user_login_failed)
def _on_login_failed(sender, credentials, request, **kwargs):
    audit.record(request, AuditEvent.Action.LOGIN_FAILED,
                 detail=f"username={credentials.get('username', '')}")


@receiver(user_locked_out)
def _on_lockout(sender, request, username, ip_address, **kwargs):
    audit.record(request, AuditEvent.Action.LOCKOUT, detail=f"username={username} ip={ip_address}")
