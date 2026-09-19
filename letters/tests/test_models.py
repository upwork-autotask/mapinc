import pytest
from django.core.management import call_command
from django.db import IntegrityError

from letters.models import AppSettings, Letter


@pytest.mark.django_db
def test_app_settings_load_creates_singleton_with_defaults():
    s = AppSettings.load()
    assert s.pk == 1
    assert s.attn_default == "UR DEPARTMENT"
    assert s.client_default == "WORLDTRIPS"
    assert s.doctor_default == "RICHARD ABDALLAH"
    assert s.pdf_filename_pattern == AppSettings.DEFAULT_FILENAME_PATTERN
    assert AppSettings.load().pk == 1
    assert AppSettings.objects.count() == 1


@pytest.mark.django_db
def test_app_settings_template_bytes(app_settings, template_bytes):
    assert app_settings.template_bytes() == template_bytes


@pytest.mark.django_db
def test_letter_case_encounter_is_unique():
    Letter.objects.create(case_encounter="E1", policy_id="P1", member_name="A", dob="1953-05-22",
                          admission="9/15/2026", attn="x", client="y", doctor="z",
                          folder_name="F", pdf_path="", docx_path="",
                          created_by="u", modified_by="u")
    with pytest.raises(IntegrityError):
        Letter.objects.create(case_encounter="E1", policy_id="P2", member_name="B", dob="1953-05-22",
                              admission="", attn="x", client="y", doctor="z",
                              folder_name="F", pdf_path="", docx_path="",
                              created_by="u", modified_by="u")


@pytest.mark.django_db
def test_letter_timestamps_are_set_automatically():
    letter = Letter.objects.create(case_encounter="E2", policy_id="P1", member_name="A", dob="1953-05-22",
                                   admission="", attn="x", client="y", doctor="z",
                                   folder_name="F", pdf_path="", docx_path="",
                                   created_by="u", modified_by="u")
    assert letter.created_at is not None and letter.modified_at is not None


@pytest.mark.django_db
def test_load_default_template_command(settings, tmp_path, template_bytes):
    settings.MEDIA_ROOT = tmp_path / "media"
    call_command("load_default_template")
    assert AppSettings.load().template_bytes() == template_bytes
    # running twice replaces rather than duplicates
    call_command("load_default_template")
    assert AppSettings.objects.count() == 1
