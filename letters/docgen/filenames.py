"""Filename pattern expansion and validation of the destination folder."""
import re
import string
from datetime import date
from pathlib import Path

from django.conf import settings

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_DRIVE = re.compile(r"^[A-Za-z]:\\")

# Everything the PDF filename pattern may refer to. The case values come from the
# Access/Outlook launcher; MMDDYY/YYYYMMDD are today's date; user is who saved it.
ALLOWED_PLACEHOLDERS = (
    "case_encounter", "policy_id", "member_name", "case_location", "case_type", "user",
    "MMDDYY", "YYYYMMDD",
)
MALFORMED = "(the pattern is malformed)"


class InvalidFolderName(ValueError):
    pass


class InvalidFilenamePattern(ValueError):
    pass


def unknown_placeholders(pattern: str) -> list[str]:
    """Placeholder names in the pattern that the app cannot fill, in order."""
    try:
        names = [name for _, name, _, _ in string.Formatter().parse(pattern or "") if name]
    except ValueError:
        return [MALFORMED]
    unknown, seen = [], set()
    for name in names:
        root = name.split(".")[0].split("[")[0]
        if root not in ALLOWED_PLACEHOLDERS and root not in seen:
            seen.add(root)
            unknown.append(root)
    return unknown


def safe_component(value: str) -> str:
    """Strip characters Windows does not allow in file names."""
    cleaned = _ILLEGAL.sub("", str(value)).strip().rstrip(".").strip()
    return cleaned or "_"


def build_filename(pattern: str, *, member_name: str, policy_id: str, case_encounter: str, today: date,
                   case_location: str = "", case_type: str = "", user: str = "") -> str:
    unknown = unknown_placeholders(pattern)
    if unknown:
        raise InvalidFilenamePattern(
            f"The PDF filename pattern uses {', '.join(unknown)}, which the app cannot fill. "
            "Use only: " + ", ".join("{" + name + "}" for name in ALLOWED_PLACEHOLDERS))
    name = pattern.format(
        member_name=safe_component(member_name),
        policy_id=safe_component(policy_id),
        case_encounter=safe_component(case_encounter),
        case_location=safe_component(case_location) if case_location else "",
        case_type=safe_component(case_type) if case_type else "",
        user=safe_component(_account_name(user)) if user else "",
        MMDDYY=today.strftime("%m%d%y"),
        YYYYMMDD=today.strftime("%Y%m%d"),
    ).strip()
    name = _tidy(name)
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


def _account_name(user: str) -> str:
    """DOMAIN\\jdoe -> jdoe (a backslash cannot appear in a file name)."""
    return str(user).rsplit("\\", 1)[-1].split("@", 1)[0]


def _tidy(name: str) -> str:
    """A blank value must not leave '--' or a dangling separator before '.pdf'."""
    name = re.sub(r"-{2,}", "-", name)
    name = re.sub(r"\s{2,}", " ", name)
    name = re.sub(r"[-\s]+(?=\.[A-Za-z0-9]+$)", "", name)
    return name.strip(" -")


def resolve_folder(folder_path: str, allowed_roots: list[str] | None = None) -> Path:
    """
    Validate the destination folder the launcher supplied. It is the whole path —
    a drive path (D:\claims\SMITH) or a UNC path (\\server\claims\SMITH).
    MAPINC_ALLOWED_FOLDER_ROOTS, when set, limits where letters may be written.
    """
    raw = (folder_path or "").strip().strip('"').strip()
    if not raw:
        raise InvalidFolderName("Folder is required. Open the letter from Access or Outlook so it is filled in.")

    path_text = raw.replace("/", "\\")
    is_unc = path_text.startswith("\\\\") and len([p for p in path_text[2:].split("\\") if p]) >= 2
    if not (_DRIVE.match(path_text) or is_unc):
        raise InvalidFolderName(
            "Folder must be a full path, for example \\\\server\\claims\\SMITH_JOHN or D:\\claims\\SMITH_JOHN.")
    if any(part == ".." for part in path_text.split("\\")):
        raise InvalidFolderName("Folder path may not contain '..'.")

    trimmed = path_text.rstrip("\\")
    if is_unc and len(trimmed) < 3:
        raise InvalidFolderName("Folder must include the share name, for example \\\\server\\claims.")
    folder = Path(trimmed)

    roots = settings.MAPINC_ALLOWED_FOLDER_ROOTS if allowed_roots is None else allowed_roots
    if roots and not any(_is_within(trimmed, root) for root in roots):
        raise InvalidFolderName(
            f"{folder} is not an allowed folder. Letters may only be written under: " + ", ".join(roots))
    return folder


def _is_within(path_text: str, root: str) -> bool:
    candidate = path_text.replace("/", "\\").rstrip("\\").casefold()
    base = (root or "").strip().replace("/", "\\").rstrip("\\").casefold()
    return bool(base) and (candidate == base or candidate.startswith(base + "\\"))
