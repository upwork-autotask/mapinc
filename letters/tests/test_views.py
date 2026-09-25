import datetime as dt
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from letters.models import Letter

BASE = {"case_encounter": "E1", "policy_id": "P1", "member_name": "JOHN SMITH", "dob": "1953-05-22",
        "admission": "9/15/2026", "user": "DOM\\bob"}


@pytest.fixture(autouse=True)
def fake_converter(settings):
    settings.PDF_CONVERTER = "fake"


@pytest.fixture
def VALID(claims_folder):
    return {**BASE, "folder_name": str(claims_folder)}


def _existing(**overrides):
    fields = dict(case_encounter="E1", policy_id="P1", member_name="OLD NAME", dob=dt.date(1953, 5, 22),
                  admission="9/1/2026", attn="a", client="c", doctor="d", folder_name=r"D:\claims\OLD",
                  pdf_path="", docx_path="", created_by="u", modified_by="u")
    return Letter.objects.create(**{**fields, **overrides})


@pytest.mark.django_db
def test_get_prefills_from_query_string(client, app_settings, VALID):
    r = client.get(reverse("letter_form"), {**VALID, "dob": "5/22/1953"})
    assert r.status_code == 200
    initial = r.context["form"].initial
    assert initial["member_name"] == "JOHN SMITH"
    assert initial["dob"] == dt.date(1953, 5, 22)
    assert initial["user"] == "DOM\\bob"
    html = r.content.decode()
    assert 'value="1953-05-22"' in html
    assert app_settings.client_default in html and app_settings.doctor_default in html


@pytest.mark.django_db
def test_folder_is_read_only_and_has_an_open_button(client, app_settings, VALID):
    html = client.get(reverse("letter_form"), VALID).content.decode()
    folder_input = [line for line in html.splitlines() if 'name="folder_name"' in line][0]
    assert "readonly" in folder_input
    assert "Open folder" in html


@pytest.mark.django_db
def test_get_prefills_from_existing_letter_with_query_override(client, app_settings):
    _existing()
    r = client.get(reverse("letter_form"), {"case_encounter": "E1", "member_name": "NEW NAME"})
    initial = r.context["form"].initial
    assert initial["member_name"] == "NEW NAME"
    assert initial["policy_id"] == "P1"
    assert initial["folder_name"] == r"D:\claims\OLD"
    assert initial["dob"] == dt.date(1953, 5, 22)


@pytest.mark.django_db
def test_get_without_parameters_shows_empty_form(client, app_settings):
    """No launcher values: the form still renders (folder stays blank and read-only)."""
    r = client.get(reverse("letter_form"))
    assert r.status_code == 200 and r.context["form"].initial == {}


@pytest.mark.django_db
def test_post_generates_and_shows_success(client, app_settings, VALID):
    r = client.post(reverse("letter_form"), VALID)
    assert r.status_code == 200
    assert "letters/success.html" in [t.name for t in r.templates]
    letter = Letter.objects.get(case_encounter="E1")
    assert letter.created_by == "DOM\\bob"
    assert letter.pdf_path in r.content.decode()
    assert reverse("letter_pdf", args=["E1"]) in r.content.decode()


@pytest.mark.django_db
def test_post_missing_fields_shows_errors_and_saves_nothing(client, app_settings):
    r = client.post(reverse("letter_form"), {"case_encounter": "E1"})
    assert r.status_code == 200
    assert "member_name" in r.context["form"].errors
    assert Letter.objects.count() == 0


@pytest.mark.django_db
def test_post_pipeline_error_is_shown_in_message_bar(client, app_settings, VALID):
    r = client.post(reverse("letter_form"), {**VALID, "folder_name": "SMITH"})  # not a full path
    assert r.status_code == 200
    assert "full path" in r.content.decode()
    assert Letter.objects.count() == 0


@pytest.mark.django_db
def test_pdf_download(client, app_settings, VALID):
    client.post(reverse("letter_form"), VALID)
    r = client.get(reverse("letter_pdf", args=["E1"]))
    assert r.status_code == 200
    assert r["Content-Type"] == "application/pdf"
    assert b"".join(r.streaming_content).startswith(b"%PDF")


@pytest.mark.django_db
def test_pdf_download_404_when_unknown_or_missing_file(client, app_settings):
    assert client.get(reverse("letter_pdf", args=["nope"])).status_code == 404
    _existing(pdf_path=r"C:\does\not\exist.pdf")
    assert client.get(reverse("letter_pdf", args=["E1"])).status_code == 404


# --- an existing letter opens in view mode with its PDF details --------------

def _input_line(html, name):
    return [line for line in html.splitlines() if f'name="{name}"' in line][0]


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser("report", "report@example.com", "pw")


@pytest.mark.django_db
def test_existing_letter_shows_pdf_details_and_view_and_edit_buttons(client, app_settings, VALID):
    client.post(reverse("letter_form"), VALID)
    letter = Letter.objects.get(case_encounter="E1")

    r = client.get(reverse("letter_form"), {"case_encounter": "E1"})
    html = r.content.decode()
    assert r.context["existing"] == letter and r.context["pdf_exists"] is True and r.context["edit_mode"] is False
    assert Path(letter.pdf_path).name in html
    assert reverse("letter_pdf", args=["E1"]) in html and "View PDF" in html
    assert letter.modified_by in html
    assert "Edit" in html and "Save &amp;" not in html          # nothing is saved from view mode
    assert "readonly" in _input_line(html, "admission")         # view mode locks every field


@pytest.mark.django_db
def test_no_panel_for_a_case_without_a_letter(client, app_settings):
    html = client.get(reverse("letter_form"), {"case_encounter": "NEW-1"}).content.decode()
    assert "View PDF" not in html and "Save &amp; Create PDF" in html
    assert "readonly" not in _input_line(html, "member_name")   # a new letter is fully editable
    assert "readonly" in _input_line(html, "folder_name")       # except the launcher's folder


@pytest.mark.django_db
def test_missing_pdf_file_is_reported_instead_of_a_dead_button(client, app_settings, VALID):
    client.post(reverse("letter_form"), VALID)
    Path(Letter.objects.get().pdf_path).unlink()
    r = client.get(reverse("letter_form"), {"case_encounter": "E1"})
    assert r.context["pdf_exists"] is False
    assert "no longer in the folder" in r.content.decode() and "View PDF" not in r.content.decode()


# --- edit mode: admission only, unless an administrator is signed in ---------

@pytest.mark.django_db
def test_edit_mode_lets_an_ordinary_user_change_only_the_admission(client, app_settings, VALID):
    client.post(reverse("letter_form"), VALID)
    html = client.get(reverse("letter_form"), {"case_encounter": "E1", "edit": "1"}).content.decode()
    assert "readonly" not in _input_line(html, "admission")
    for locked in ("member_name", "policy_id", "dob", "folder_name", "case_encounter"):
        assert "readonly" in _input_line(html, locked), locked
    assert "Save &amp; Replace PDF" in html


@pytest.mark.django_db
def test_edit_mode_lets_an_administrator_change_everything(client, app_settings, VALID, admin_user):
    client.post(reverse("letter_form"), VALID)
    client.force_login(admin_user)
    html = client.get(reverse("letter_form"), {"case_encounter": "E1", "edit": "1"}).content.decode()
    for name in ("admission", "member_name", "policy_id", "dob", "folder_name", "case_encounter"):
        assert "readonly" not in _input_line(html, name), name


@pytest.mark.django_db
def test_posted_changes_to_locked_fields_are_ignored_for_ordinary_users(client, app_settings, VALID):
    client.post(reverse("letter_form"), VALID)
    r = client.post(reverse("letter_form"), {**VALID, "member_name": "SOMEONE ELSE",
                                             "admission": "9/30/2026", "user": "DOM\jane"})
    assert r.status_code == 200
    letter = Letter.objects.get()
    assert letter.member_name == "JOHN SMITH"      # locked field kept its stored value
    assert letter.admission == "9/30/2026"         # the one field they may change
    assert letter.modified_by == "DOM\jane"


@pytest.mark.django_db
def test_an_administrator_may_post_changes_to_every_field(client, app_settings, VALID, admin_user, tmp_path):
    client.post(reverse("letter_form"), VALID)
    client.force_login(admin_user)
    other = tmp_path / "claims" / "MOVED"
    r = client.post(reverse("letter_form"), {**VALID, "member_name": "JANE SMITH", "folder_name": str(other)})
    assert r.status_code == 200
    letter = Letter.objects.get()
    assert letter.member_name == "JANE SMITH" and Path(letter.pdf_path).parent == other
