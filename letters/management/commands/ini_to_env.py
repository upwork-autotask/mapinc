"""
One-time migration from the old mapinc.ini to the .env file.

    python manage.py ini_to_env            # reads mapinc.ini, writes .env
    python manage.py ini_to_env --ini path\\to\\other.ini --out path\\to\\.env.migrate
"""
import configparser
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# ini section/key -> environment variable
MAPPING = {
    ("database", "host"): "MAPINC_DB_HOST",
    ("database", "port"): "MAPINC_DB_PORT",
    ("database", "name"): "MAPINC_DB_NAME",
    ("database", "user"): "MAPINC_DB_USER",
    ("database", "password"): "MAPINC_DB_PASSWORD",
    ("database", "sslmode"): "MAPINC_DB_SSLMODE",
    ("database", "sslrootcert"): "MAPINC_DB_SSLROOTCERT",
    ("app", "secret_key"): "MAPINC_SECRET_KEY",
    ("app", "allowed_hosts"): "MAPINC_ALLOWED_HOSTS",
    ("app", "debug"): "MAPINC_DEBUG",
    ("app", "pdf_converter"): "MAPINC_PDF_CONVERTER",
    ("app", "word_timeout_seconds"): "MAPINC_WORD_TIMEOUT_SECONDS",
    ("app", "production"): "MAPINC_PRODUCTION",
    ("app", "https"): "MAPINC_HTTPS",
    ("app", "behind_proxy"): "MAPINC_BEHIND_PROXY",
    ("app", "auth_mode"): "MAPINC_AUTH_MODE",
    ("app", "session_minutes"): "MAPINC_SESSION_MINUTES",
    ("app", "lockout_failures"): "MAPINC_LOCKOUT_FAILURES",
    ("app", "lockout_minutes"): "MAPINC_LOCKOUT_MINUTES",
    ("app", "allow_query_prefill"): "MAPINC_ALLOW_QUERY_PREFILL",
    ("app", "handoff_allowed_networks"): "MAPINC_HANDOFF_ALLOWED_NETWORKS",
    ("app", "handoff_minutes"): "MAPINC_HANDOFF_MINUTES",
}


def convert(ini_text: str) -> str:
    parser = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    parser.read_string(ini_text)
    lines = ["# Converted from mapinc.ini by `manage.py ini_to_env`"]
    for (section, key), var in MAPPING.items():
        if parser.has_option(section, key):
            value = parser.get(section, key).strip()
            if any(ch in value for ch in " #'\""):
                value = '"' + value.replace('"', '\\"') + '"'
            lines.append(f"{var}={value}")
    return "\n".join(lines) + "\n"


class Command(BaseCommand):
    help = "Convert the old mapinc.ini into a .env file."

    def add_arguments(self, parser):
        parser.add_argument("--ini", default=str(settings.BASE_DIR / "mapinc.ini"))
        parser.add_argument("--out", default=str(settings.BASE_DIR / ".env"))
        parser.add_argument("--force", action="store_true", help="overwrite an existing output file")

    def handle(self, *args, **options):
        ini, out = Path(options["ini"]), Path(options["out"])
        if not ini.is_file():
            raise CommandError(f"{ini} not found")
        if out.exists() and not options["force"]:
            raise CommandError(f"{out} already exists; use --force to overwrite")
        out.write_text(convert(ini.read_text(encoding="utf-8")), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Wrote {out}. Review it, then delete {ini}."))
