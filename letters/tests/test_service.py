import datetime as dt
from pathlib import Path

import pytest

from letters.docgen.pdf_convert import ConversionError
from letters.docgen.service import LetterGenerationError, generate_letter
from letters.models import Letter
from letters.tests.test_template_fill import _sdt_texts

DATA = dict(case_encounter="E-100", policy_id="WT-123456", member_name="JOHN SMITH",
            dob=dt.date(1953, 5, 22), admission="9/15/2026", folder_name="SMITH_JOHN")


@pytest.fixture(autouse=True)
def fake_converter(settings):
    settings.PDF_CONVERTER = "fake"


@pytest.mark.django_db
def test_creates_letter_files_and_audit_fields(app_settings):
    letter = generate_letter(DATA, "DOMAIN\rabdallah")
    pdf = Path(letter.pdf_path)
    assert pdf.parent == Path(app_settings.pdf_root_folder) / "SMITH_JOHN"
    assert pdf.name.startswith("CLINICALS REQUEST-JOHN SMITH-SENT") and pdf.suffix == ".pdf"
    assert pdf.read_bytes().startswith(b"%PDF")
    assert Path(letter.docx_path) == pdf.with_suffix(".docx") and Path(letter.docx_path).exists()
    assert (letter.attn, letter.client, letter.doctor) == ("UR DEPARTMENT", "WORLDTRIPS", "RICHARD ABDALLAH")
    assert letter.created_by == letter.modified_by == "DOMAIN\rabdallah"
    assert letter.created_at is not None and letter.modified_at is not None
    assert Letter.objects.count() == 1


@pytest.mark.django_db
def test_docx_contains_the_values_and_snapshotted_defaults(app_settings):
    letter = generate_letter(DATA, "u")
    texts = _sdt_texts(Path(letter.docx_path).read_bytes())
    assert texts["keywords"] == ["WT-123456"]
    assert texts["PublishDate"] == ["5/22/1953"]
    assert texts["Company"] == ["WORLDTRIPS", "WORLDTRIPS"]


@pytest.mark.django_db
def test_update_keeps_created_by_and_replaces_old_files(app_settings):
    first = generate_letter(DATA, "alice")
    old_pdf, old_docx = Path(first.pdf_path), Path(first.docx_path)
    second = generate_letter({**DATA, "member_name": "JANE SMITH"}, "bob")
    assert second.pk == first.pk
    assert (second.created_by, second.modified_by) == ("alice", "bob")
    assert second.modified_at > first.modified_at
    assert second.member_name == "JANE SMITH"
    assert not old_pdf.exists() and not old_docx.exists()
    assert Path(second.pdf_path).exists() and "JANE SMITH" in second.pdf_path
    assert Letter.objects.count() == 1


@pytest.mark.django_db
def test_blank_user_becomes_unknown(app_settings):
    assert generate_letter(DATA, "  ").created_by == "unknown"


@pytest.mark.django_db
def test_invalid_folder_name_saves_nothing(app_settings):
    with pytest.raises(LetterGenerationError):
        generate_letter({**DATA, "folder_name": r"..\x"}, "u")
    assert Letter.objects.count() == 0


@pytest.mark.django_db
def test_missing_root_folder_is_reported(app_settings):
    app_settings.pdf_root_folder = ""
    app_settings.save()
    with pytest.raises(LetterGenerationError, match="root folder"):
        generate_letter(DATA, "u")


@pytest.mark.django_db
def test_converter_failure_saves_nothing(app_settings, monkeypatch):
    def boom(*args, **kwargs):
        raise ConversionError("Word exploded")

    monkeypatch.setattr("letters.docgen.service.convert", boom)
    with pytest.raises(LetterGenerationError, match="Word exploded"):
        generate_letter(DATA, "u")
    assert Letter.objects.count() == 0


@pytest.mark.django_db
def test_missing_required_field(app_settings):
    with pytest.raises(LetterGenerationError, match="member_name"):
        generate_letter({**DATA, "member_name": ""}, "u")
