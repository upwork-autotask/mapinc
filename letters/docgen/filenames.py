"""Filename pattern expansion and safe sub-folder resolution."""
import re
from datetime import date
from pathlib import Path

_ILLEGAL = re.compile(r'[<>:"/\|?*\x00-\x1f]')


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


def resolve_folder(root: str, folder_name: str) -> Path:
    """Join `folder_name` (from the query string) under `root` (from admin settings), refusing escapes."""
    if not (root or "").strip():
        raise InvalidFolderName("PDF root folder is not set. Set it in admin > Settings.")
    name = (folder_name or "").strip().replace("/", "\\")
    if not name:
        raise InvalidFolderName("Folder name is required.")
    if name.startswith("\\"):
        raise InvalidFolderName("Folder name must be a sub-folder name, not an absolute path.")
    parts = [p.strip() for p in name.split("\\") if p.strip()]
    if any(p == ".." or ":" in p for p in parts):
        raise InvalidFolderName("Folder name may not contain '..' or a drive letter.")
    return Path(root.strip()).joinpath(*parts)
