"""Generate one Clinicals Request letter end to end and record it."""
import logging
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from letters.models import AppSettings, Letter

from .filenames import InvalidFolderName, build_filename, resolve_folder
from .pdf_convert import ConversionError, convert
from .template_fill import fill_template

log = logging.getLogger(__name__)

REQUIRED_FIELDS = ("case_encounter", "policy_id", "member_name", "dob", "admission", "folder_name")


class LetterGenerationError(Exception):
    """Something the user can act on; the message is shown on the form."""


def generate_letter(data: dict, windows_user: str) -> Letter:
    for key in REQUIRED_FIELDS:
        if not data.get(key):
            raise LetterGenerationError(f"{key} is required.")
    windows_user = (windows_user or "").strip() or "unknown"

    s = AppSettings.load()
    values = dict(
        policy_id=data["policy_id"], member_name=data["member_name"], dob=data["dob"],
        admission=data["admission"],
        attn=s.attn_default, client=s.client_default, doctor=s.doctor_default,
    )
    try:
        folder = resolve_folder(s.pdf_root_folder, data["folder_name"])
        template = s.template_bytes()
    except (InvalidFolderName, ValueError) as exc:
        raise LetterGenerationError(str(exc)) from exc

    docx_bytes = fill_template(template, values)
    pdf_path = folder / build_filename(
        s.pdf_filename_pattern, member_name=data["member_name"], policy_id=data["policy_id"],
        case_encounter=data["case_encounter"], today=timezone.localdate())
    docx_path = pdf_path.with_suffix(".docx")

    try:
        folder.mkdir(parents=True, exist_ok=True)
        docx_path.write_bytes(docx_bytes)
        convert(docx_path, pdf_path)
    except (OSError, ConversionError) as exc:
        log.exception("Letter generation failed for case %s", data["case_encounter"])
        raise LetterGenerationError(f"Could not create the PDF: {exc}") from exc

    with transaction.atomic():
        letter = Letter.objects.filter(case_encounter=data["case_encounter"]).first()
        if letter is None:
            letter = Letter(case_encounter=data["case_encounter"], created_by=windows_user)
        else:
            _delete_old_files(letter, keep={str(pdf_path), str(docx_path)})
        letter.policy_id = data["policy_id"]
        letter.member_name = data["member_name"]
        letter.dob = data["dob"]
        letter.admission = data["admission"]
        letter.attn, letter.client, letter.doctor = values["attn"], values["client"], values["doctor"]
        letter.folder_name = data["folder_name"]
        letter.pdf_path = str(pdf_path)
        letter.docx_path = str(docx_path)
        letter.modified_by = windows_user
        letter.save()
    return letter


def _delete_old_files(letter: Letter, keep: set[str]) -> None:
    for old in (letter.pdf_path, letter.docx_path):
        if old and old not in keep:
            try:
                Path(old).unlink(missing_ok=True)
            except OSError:
                log.warning("Could not delete superseded file %s", old, exc_info=True)
