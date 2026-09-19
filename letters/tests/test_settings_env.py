"""The settings module reads MAPINC_* environment variables (optionally from a .env file)."""
import importlib
import sys

import pytest
from django.conf import settings

from mapinc import env as envmod


def _load_settings(monkeypatch, tmp_path, env: dict, dotenv: str | None = None):
    """Import mapinc.settings fresh with only the given environment."""
    for name in [k for k in list(__import__("os").environ) if k.startswith("MAPINC_")]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MAPINC_ENV_FILE", str(tmp_path / ".env"))
    if dotenv is not None:
        (tmp_path / ".env").write_text(dotenv, encoding="utf-8")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop("mapinc.settings", None)
    return importlib.import_module("mapinc.settings")


def test_current_settings_come_from_environment():
    db = settings.DATABASES["default"]
    assert db["ENGINE"] == "django.db.backends.postgresql"
    assert db["NAME"] in {envmod.get("MAPINC_DB_NAME", "mapinc"), "test_" + envmod.get("MAPINC_DB_NAME", "mapinc")}
    assert settings.PDF_CONVERTER in {"word", "libreoffice", "fake"}
    assert isinstance(settings.WORD_TIMEOUT_SECONDS, int)


def test_defaults_when_nothing_is_set(monkeypatch, tmp_path):
    s = _load_settings(monkeypatch, tmp_path, {})
    assert s.DATABASES["default"]["HOST"] == "localhost"
    assert s.DATABASES["default"]["OPTIONS"]["sslmode"] == "prefer"
    assert s.DEBUG is False and s.MAPINC_PRODUCTION is False
    assert s.MAPINC_AUTH_MODE == "open" and s.MAPINC_SESSION_MINUTES == 30
    assert s.ALLOWED_HOSTS == ["*"]


def test_values_from_process_environment(monkeypatch, tmp_path):
    s = _load_settings(monkeypatch, tmp_path, {
        "MAPINC_DB_HOST": "db.map.local", "MAPINC_DB_SSLMODE": "verify-full", "MAPINC_DB_SSLROOTCERT": r"C:\ca.crt",
        "MAPINC_DEBUG": "true", "MAPINC_ALLOWED_HOSTS": "letters.map.local, 10.0.0.5",
        "MAPINC_AUTH_MODE": "LOGIN", "MAPINC_SESSION_MINUTES": "12", "MAPINC_HANDOFF_ALLOWED_NETWORKS": "10.0.0.0/8,127.0.0.1/32",
    })
    db = s.DATABASES["default"]
    assert db["HOST"] == "db.map.local"
    assert db["OPTIONS"] == {"sslmode": "verify-full", "sslrootcert": r"C:\ca.crt"}
    assert s.DEBUG is True
    assert s.ALLOWED_HOSTS == ["letters.map.local", "10.0.0.5"]
    assert s.MAPINC_AUTH_MODE == "login" and s.MAPINC_SESSION_MINUTES == 12
    assert s.MAPINC_HANDOFF_ALLOWED_NETWORKS == ["10.0.0.0/8", "127.0.0.1/32"]


def test_dotenv_file_is_read_but_process_environment_wins(monkeypatch, tmp_path):
    s = _load_settings(monkeypatch, tmp_path, {"MAPINC_DB_NAME": "from_process"},
                       dotenv="# comment\nMAPINC_DB_NAME=from_file\nMAPINC_DB_USER='quoted user'\nMAPINC_SECRET_KEY=\"k=e=y\"\n\n")
    db = s.DATABASES["default"]
    assert db["NAME"] == "from_process"
    assert db["USER"] == "quoted user"
    assert s.SECRET_KEY == "k=e=y"


def test_invalid_auth_mode_is_rejected(monkeypatch, tmp_path):
    with pytest.raises(RuntimeError, match="MAPINC_AUTH_MODE"):
        _load_settings(monkeypatch, tmp_path, {"MAPINC_AUTH_MODE": "magic"})


def test_bad_boolean_is_rejected(monkeypatch, tmp_path):
    with pytest.raises(RuntimeError, match="MAPINC_DEBUG"):
        _load_settings(monkeypatch, tmp_path, {"MAPINC_DEBUG": "maybe"})


def test_https_defaults_to_production_flag(monkeypatch, tmp_path):
    s = _load_settings(monkeypatch, tmp_path, {"MAPINC_PRODUCTION": "1"})
    assert s.MAPINC_HTTPS is True and s.MAPINC_ALLOW_QUERY_PREFILL is False and s.SESSION_COOKIE_SECURE is True


def test_ini_to_env_conversion(tmp_path):
    from django.core.management import call_command

    from letters.management.commands.ini_to_env import convert

    ini = tmp_path / "mapinc.ini"
    ini.write_text("[database]\nhost = db1\npassword = p a#ss ; comment\n\n[app]\nsecret_key = abc\nauth_mode = login\n",
                   encoding="utf-8")
    text = convert(ini.read_text())
    assert "MAPINC_DB_HOST=db1" in text
    assert 'MAPINC_DB_PASSWORD="p a#ss"' in text  # trailing ; comment stripped, quoted because of space and #
    assert "MAPINC_AUTH_MODE=login" in text and "MAPINC_DB_PORT" not in text

    out = tmp_path / ".env"
    call_command("ini_to_env", ini=str(ini), out=str(out))
    assert out.read_text().startswith("# Converted")
    with pytest.raises(Exception):
        call_command("ini_to_env", ini=str(ini), out=str(out))  # refuses to overwrite without --force
