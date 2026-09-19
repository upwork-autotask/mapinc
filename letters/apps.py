from django.apps import AppConfig


class LettersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "letters"

    def ready(self):
        from . import checks  # noqa: F401  registers the production config checks
