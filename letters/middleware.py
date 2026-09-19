from django.conf import settings
from django.contrib.auth.middleware import RemoteUserMiddleware
from django.utils.cache import add_never_cache_headers


class NoStoreMiddleware:
    """ePHI pages must never be cached on the client; static assets may be."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith(settings.STATIC_URL if settings.STATIC_URL.startswith("/")
                                       else "/" + settings.STATIC_URL):
            add_never_cache_headers(response)
        return response


class WindowsUserMiddleware(RemoteUserMiddleware):
    """
    auth_mode = remote_user: IIS performs Windows Authentication and forwards the
    logon name in X-Remote-User (DOMAIN + backslash + user). Only enabled in that mode, so the
    header cannot be spoofed when IIS is not in front.
    """

    header = "HTTP_X_REMOTE_USER"
