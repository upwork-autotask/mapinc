from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render


def letter_access(view):
    """
    Letter form / PDF: open to the LAN when auth_mode = open; otherwise the
    user must be authenticated (app login, or IIS Windows Authentication in
    remote_user mode, which satisfies this automatically).
    """

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if settings.MAPINC_AUTH_MODE != "open" and not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        return view(request, *args, **kwargs)

    return wrapped


def staff_required(view):
    """Login required, and the user must be staff (Settings/Letters/Audit pages)."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_staff:
            return render(request, "letters/forbidden.html", status=403)
        return view(request, *args, **kwargs)

    return wrapped
