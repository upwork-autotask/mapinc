import datetime as dt
from pathlib import Path

import pytest

from letters.docgen.pdf_convert import ConversionError
from letters.docgen.service import LetterGenerationError, generate_letter
from letters.models import Letter
from letters.tests.test_template_fill import _sdt_texts

BASE = dict(case_encounter="E-100", policy_id="WT-123456", member_name="JOHN SMITH",
            dob=dt.date(1953, 5, 22), admission="9/15/2026")


@pytest.fixture(autouse=True)
def fake_converter(settings):
    settings.PDF_CONVERTER = "fake"


@pytest.fixture
def DATA(claims_folder):
    """Letter values with the full destination folder, as the launcher supplies it."""
    return {**BASE, "folder_name": str(claims_folder)}


@pytest.mark.django_db
def test_creates_letter_files_and_audit_fields(app_settings, DATA, claims_folder):
    letter = generate_letter(DATA, "DOMAIN\\rabdallah")
    pdf = Path(letter.pdf_path)
    assert pdf.parent == claims_folder
    # default pattern: case, letter title, member, date, who saved it (blank case values dropped)
    assert pdf.name.startswith("E-100-CLINICALS REQUEST-JOHN SMITH-SENT") and pdf.suffix == ".pdf"
    assert pdf.name.endswith("-rabdallah.pdf")
    assert pdf.read_bytes().startswith(b"%PDF")
    assert Path(letter.docx_path) == pdf.with_suffix(".docx") and Path(letter.docx_path).exists()
    assert (letter.attn, letter.client, letter.doctor) == ("UR DEPARTMENT", "WORLDTRIPS", "RICHARD ABDALLAH")
    assert letter.created_by == letter.modified_by == "DOMAIN\\rabdallah"
    assert letter.created_at is not None and letter.modified_at is not None
    assert Letter.objects.count() == 1


@pytest.mark.django_db
def test_docx_contains_the_values_and_snapshotted_defaults(app_settings, DATA):
    letter = generate_letter(DATA, "u")
    texts = _sdt_texts(Path(letter.docx_path).read_bytes())
    assert texts["keywords"] == ["WT-123456"]
    assert texts["PublishDate"] == ["5/22/1953"]
    assert texts["Company"] == ["WORLDTRIPS", "WORLDTRIPS"]


@pytest.mark.django_db
def test_update_keeps_created_by_and_replaces_old_files(app_settings, DATA):
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
def test_blank_user_becomes_unknown(app_settings, DATA):
    assert generate_letter(DATA, "  ").created_by == "unknown"


@pytest.mark.django_db
def test_invalid_folder_name_saves_nothing(app_settings, DATA):
    with pytest.raises(LetterGenerationError):
        generate_letter({**DATA, "folder_name": r"SMITH_JOHN"}, "u")  # not a full path
    assert Letter.objects.count() == 0


@pytest.mark.django_db
def test_folder_outside_the_allowed_roots_is_reported(app_settings, DATA, settings, tmp_path):
    settings.MAPINC_ALLOWED_FOLDER_ROOTS = [str(tmp_path / "elsewhere")]
    with pytest.raises(LetterGenerationError, match="not an allowed"):
        generate_letter(DATA, "u")
    assert Letter.objects.count() == 0


@pytest.mark.django_db
def test_converter_failure_saves_nothing(app_settings, DATA, monkeypatch):
    def boom(*args, **kwargs):
        raise ConversionError("Word exploded")

    monkeypatch.setattr("letters.docgen.service.convert", boom)
    with pytest.raises(LetterGenerationError, match="Word exploded"):
        generate_letter(DATA, "u")
    assert Letter.objects.count() == 0


@pytest.mark.django_db
def test_missing_required_field(app_settings, DATA):
    with pytest.raises(LetterGenerationError, match="member_name"):
        generate_letter({**DATA, "member_name": ""}, "u")


@pytest.mark.django_db
def test_unknown_filename_placeholder_is_a_user_error(app_settings, DATA):
    app_settings.pdf_filename_pattern = "{map_id}-{member_name}.pdf"
    app_settings.save()
    with pytest.raises(LetterGenerationError, match="map_id"):
        generate_letter(DATA, "u")
    assert Letter.objects.count() == 0


@pytest.mark.django_db
def test_case_location_and_type_are_stored_and_used_in_the_filename(app_settings, DATA):
    app_settings.pdf_filename_pattern = ("{case_encounter}-{case_location}-{case_type}-"
                                         "CLINICALS REQUEST-{member_name}-SENT{MMDDYY}-{user}.pdf")
    app_settings.save()
    letter = generate_letter({**DATA, "case_location": "MIAMI", "case_type": "INPATIENT"}, "MAP\\rabdallah")
    assert (letter.case_location, letter.case_type) == ("MIAMI", "INPATIENT")
    name = Path(letter.pdf_path).name
    assert name.startswith("E-100-MIAMI-INPATIENT-CLINICALS REQUEST-JOHN SMITH-SENT")
    assert name.endswith("-rabdallah.pdf")
