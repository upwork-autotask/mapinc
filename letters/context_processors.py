from django.conf import settings


def mapinc(request):
    return {
        "auth_mode": settings.MAPINC_AUTH_MODE,
        "folder_protocol": settings.MAPINC_FOLDER_PROTOCOL,
    }
