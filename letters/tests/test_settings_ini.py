from django.conf import settings


def test_database_comes_from_ini():
    db = settings.DATABASES["default"]
    assert db["ENGINE"] == "django.db.backends.postgresql"
    ini_name = settings.MAPINC_CONFIG["database"]["name"]
    assert db["NAME"] in {ini_name, f"test_{ini_name}"}  # pytest-django swaps in the test DB name
    assert db["HOST"] == settings.MAPINC_CONFIG["database"]["host"]


def test_app_settings_come_from_ini():
    assert settings.PDF_CONVERTER in {"word", "libreoffice", "fake"}
    assert isinstance(settings.WORD_TIMEOUT_SECONDS, int)
    assert "letters" in settings.INSTALLED_APPS
