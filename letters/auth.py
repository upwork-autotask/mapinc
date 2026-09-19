from django.contrib.auth.backends import RemoteUserBackend


class WindowsUserBackend(RemoteUserBackend):
    """Creates a non-staff Django user for each Windows account on first sight."""

    create_unknown_user = True

    def clean_username(self, username):
        # "DOMAIN\jdoe" -> "jdoe"; user@domain -> user
        return username.rsplit("\\", 1)[-1].split("@", 1)[0].lower()

    def configure_user(self, request, user, created=True):
        if created:
            user.is_staff = False
            user.set_unusable_password()
            user.save()
        return user
