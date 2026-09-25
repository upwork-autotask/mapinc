import datetime as dt
import io
import zipfile

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from lxml import etree

from letters.docgen.template_fill import missing_bindings
from letters.models import AppSettings, Letter

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

SETTINGS_POST = {
    "attn_default": "UR DEPT", "client_default": "WORLDTRIPS", "doctor_default": "RICHARD ABDALLAH",
    "pdf_filename_pattern": AppSettings.DEFAULT_FILENAME_PATTERN, "_save": "Save",
}


@pytest.fixture
def admin_client(client, db):
    client.force_login(User.objects.create_superuser("admin", "admin@example.com", "pw"))
    return client


def _template_without(template_bytes: bytes, binding: str) -> bytes:
    """Copy of the template with every content-control binding to `binding` removed."""
    src = zipfile.ZipFile(io.BytesIO(template_bytes))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/document.xml":
                root = etree.fromstring(data)
                for el in list(root.iter(f"{{{W}}}dataBinding")):
                    if el.get(f"{{{W}}}xpath", "").endswith(f":{binding}[1]"):
                        el.getparent().remove(el)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            out.writestr(item, data)
    return buf.getvalue()


def test_missing_bindings(template_bytes):
    assert missing_bindings(template_bytes) == set()
    assert missing_bindings(_template_without(template_bytes, "keywords")) == {"policy_id"}


@pytest.mark.django_db
def test_settings_changelist_redirects_to_the_single_row(admin_client):
    r = admin_client.get(reverse("admin:letters_appsettings_changelist"))
    assert r.status_code == 302
    assert r.url == reverse("admin:letters_appsettings_change", args=[1])


@pytest.mark.django_db
def test_settings_page_renders_and_saves(admin_client, app_settings):
    url = reverse("admin:letters_appsettings_change", args=[1])
    assert admin_client.get(url).status_code == 200
    r = admin_client.post(url, SETTINGS_POST)
    assert r.status_code == 302
    s = AppSettings.load()
    assert s.attn_default == "UR DEPT"
    assert s.template  # existing upload kept when no new file is sent


@pytest.mark.django_db
def test_template_upload_accepts_the_real_template(admin_client, app_settings, template_bytes):
    url = reverse("admin:letters_appsettings_change", args=[1])
    r = admin_client.post(url, {**SETTINGS_POST, "template": SimpleUploadedFile("new.docx", template_bytes)})
    assert r.status_code == 302
    assert AppSettings.load().template_bytes() == template_bytes


@pytest.mark.django_db
def test_template_upload_rejects_docx_missing_a_binding(admin_client, app_settings, template_bytes):
    url = reverse("admin:letters_appsettings_change", args=[1])
    bad = _template_without(template_bytes, "keywords")
    r = admin_client.post(url, {**SETTINGS_POST, "template": SimpleUploadedFile("bad.docx", bad)})
    assert r.status_code == 200
    assert "policy_id" in r.content.decode()
    assert AppSettings.load().template_bytes() == template_bytes


@pytest.mark.django_db
def test_letters_list_and_regenerate_action(admin_client, app_settings, settings, claims_folder):
    settings.PDF_CONVERTER = "fake"
    letter = Letter.objects.create(
        case_encounter="E1", policy_id="P1", member_name="JOHN SMITH", dob=dt.date(1953, 5, 22),
        admission="9/15/2026", attn="a", client="c", doctor="d", folder_name=str(claims_folder),
        pdf_path="", docx_path="", created_by="bob", modified_by="bob")
    r = admin_client.get(reverse("admin:letters_letter_changelist"))
    assert r.status_code == 200 and "JOHN SMITH" in r.content.decode()

    r = admin_client.post(reverse("admin:letters_letter_changelist"),
                          {"action": "regenerate_pdf", "_selected_action": [letter.pk]}, follow=True)
    letter.refresh_from_db()
    assert letter.pdf_path.endswith(".pdf")
    assert (letter.created_by, letter.modified_by) == ("bob", "admin")
    assert "PDF regenerated" in r.content.decode()


@pytest.mark.django_db
def test_letters_cannot_be_added_in_admin(admin_client):
    assert admin_client.get(reverse("admin:letters_letter_add")).status_code == 403
