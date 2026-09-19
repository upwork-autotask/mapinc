"""
Configuration from environment variables.

Every setting is a MAPINC_* variable. For convenience a `.env` file next to
manage.py (or the file named by MAPINC_ENV_FILE) is read first; real
environment variables always override it. Lines look like KEY=value, with
optional single or double quotes around the value; # starts a comment.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
_loaded_from: Path | None = None


def _parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.lower().startswith("export "):
            key = key[7:].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def load_dotenv() -> None:
    """Populate os.environ from the .env file without overriding existing variables."""
    global _loaded_from
    path = Path(os.environ.get("MAPINC_ENV_FILE") or BASE_DIR / ".env")
    if _loaded_from == path:
        return
    _loaded_from = path
    if path.is_file():
        for key, value in _parse_dotenv(path).items():
            os.environ.setdefault(key, value)


def get(name: str, default: str = "") -> str:
    load_dotenv()
    return os.environ.get(name, default).strip()


def get_bool(name: str, default: bool) -> bool:
    raw = get(name, "").lower()
    if raw == "":
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true or false (got {raw!r})")


def get_int(name: str, default: int) -> int:
    raw = get(name, "")
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be a whole number (got {raw!r})") from None


def get_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in get(name, default).split(",") if item.strip()]
