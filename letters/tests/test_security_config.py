import pytest
from django.conf import settings as dj_settings
from django.urls import reverse

from letters import checks as security_checks


# --- response headers -------------------------------------------------------

@pytest.mark.django_db
def test_app_pages_are_never_cached(client, app_settings):
    r = client.get(reverse("letter_form"))
    assert "no-store" in r["Cache-Control"]
    r = client.get(reverse("login"))
    assert "no-store" in r["Cache-Control"]


def test_static_files_are_cacheable(client):
    r = client.get("/static/letters/access.css")
    assert "no-store" not in r.get("Cache-Control", "")


@pytest.mark.django_db
def test_pdf_download_is_never_cached(client, app_settings, settings):
    settings.PDF_CONVERTER = "fake"
    client.post(reverse("letter_form"), {"case_encounter": "E1", "policy_id": "P1", "member_name": "A B",
                                         "dob": "1953-05-22", "admission": "x", "folder_name": "F"})
    r = client.get(reverse("letter_pdf", args=["E1"]))
    assert r.status_code == 200 and "no-store" in r["Cache-Control"]


def test_clickjacking_denied():
    assert dj_settings.X_FRAME_OPTIONS == "DENY"


def test_session_hardening_defaults():
    assert dj_settings.SESSION_COOKIE_AGE == dj_settings.MAPINC_SESSION_MINUTES * 60
    assert dj_settings.SESSION_EXPIRE_AT_BROWSER_CLOSE is True
    assert dj_settings.SESSION_SAVE_EVERY_REQUEST is True
    assert dj_settings.SESSION_COOKIE_HTTPONLY is True


def test_database_sslmode_comes_from_ini():
    opts = dj_settings.DATABASES["default"]["OPTIONS"]
    assert opts["sslmode"] == dj_settings.MAPINC_CONFIG["database"].get("sslmode", "prefer")


# --- production startup checks -----------------------------------------------

def _run_checks(settings, monkeypatch, **overrides):
    settings.MAPINC_PRODUCTION = True
    defaults = dict(DEBUG=False, SECRET_KEY="x" * 50, ALLOWED_HOSTS=["letters.map.local"],
                    MAPINC_AUTH_MODE="remote_user", MAPINC_HTTPS=True, MAPINC_ALLOW_QUERY_PREFILL=False)
    defaults.update({k: v for k, v in overrides.items() if k not in ("DB_USER", "SSLMODE")})
    for name, value in defaults.items():
        setattr(settings, name, value)
    db = dj_settings.DATABASES["default"]
    monkeypatch.setitem(db, "USER", overrides.get("DB_USER", "mapinc_app"))
    monkeypatch.setitem(db["OPTIONS"], "sslmode", overrides.get("SSLMODE", "require"))
    return [c.id for c in security_checks.production_config(app_configs=None)]


def test_hardened_config_passes(settings, monkeypatch):
    assert _run_checks(settings, monkeypatch) == []


@pytest.mark.parametrize("override, expected", [
    ({"DEBUG": True}, "letters.E001"),
    ({"SECRET_KEY": "change-me-to-a-long-random-string"}, "letters.E002"),
    ({"SECRET_KEY": "short"}, "letters.E002"),
    ({"ALLOWED_HOSTS": ["*"]}, "letters.E003"),
    ({"SSLMODE": "prefer"}, "letters.E004"),
    ({"SSLMODE": "disable"}, "letters.E004"),
    ({"DB_USER": "mapinc"}, "letters.E005"),
    ({"DB_USER": "postgres"}, "letters.E005"),
    ({"MAPINC_AUTH_MODE": "open"}, "letters.E006"),
    ({"MAPINC_HTTPS": False}, "letters.E007"),
    ({"MAPINC_ALLOW_QUERY_PREFILL": True}, "letters.E008"),
])
def test_unsafe_production_config_is_rejected(settings, monkeypatch, override, expected):
    assert expected in _run_checks(settings, monkeypatch, **override)


def test_checks_are_silent_outside_production(settings):
    settings.MAPINC_PRODUCTION = False
    settings.DEBUG = True
    assert security_checks.production_config(app_configs=None) == []
