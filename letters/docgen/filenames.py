"""Filename pattern expansion and validation of the destination folder."""
import re
from datetime import date
from pathlib import Path

from django.conf import settings

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_DRIVE = re.compile(r"^[A-Za-z]:\\")


class InvalidFolderName(ValueError):
    pass


def safe_component(value: str) -> str:
    """Strip characters Windows does not allow in file names."""
    cleaned = _ILLEGAL.sub("", str(value)).strip().rstrip(".").strip()
    return cleaned or "_"


def build_filename(pattern: str, *, member_name: str, policy_id: str, case_encounter: str, today: date) -> str:
    name = pattern.format(
        member_name=safe_component(member_name),
        policy_id=safe_component(policy_id),
        case_encounter=safe_component(case_encounter),
        MMDDYY=today.strftime("%m%d%y"),
        YYYYMMDD=today.strftime("%Y%m%d"),
    ).strip()
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


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
