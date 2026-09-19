from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render


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
