import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from letters.models import AppSettings
from letters.tests.test_admin import _template_without

SETTINGS_POST = {
    "attn_default": "UR DEPT", "client_default": "WORLDTRIPS", "doctor_default": "RICHARD ABDALLAH",
    "pdf_root_folder": r"\\server\claims", "pdf_filename_pattern": AppSettings.DEFAULT_FILENAME_PATTERN,
}


@pytest.fixture
def staff(db):
    return User.objects.create_superuser("report", "report@example.com", "pw")


@pytest.mark.django_db
def test_login_page_is_branded(client):
    r = client.get(reverse("login"))
    assert r.status_code == 200
    html = r.content.decode()
    assert "map_logo.jpg" in html and 'name="username"' in html and 'name="password"' in html


@pytest.mark.django_db
def test_login_success_redirects_to_settings(client, staff):
    r = client.post(reverse("login"), {"username": "report", "password": "pw"})
    assert r.status_code == 302 and r.url == reverse("settings")


@pytest.mark.django_db
def test_login_failure_shows_error(client, staff):
    r = client.post(reverse("login"), {"username": "report", "password": "wrong"})
    assert r.status_code == 200
    assert "Please try again" in r.content.decode()


@pytest.mark.django_db
def test_login_honours_next(client, staff):
    r = client.post(reverse("login") + "?next=/admin/", {"username": "report", "password": "pw"})
    assert r.status_code == 302 and r.url == "/admin/"


@pytest.mark.django_db
def test_settings_requires_login(client):
    r = client.get(reverse("settings"))
    assert r.status_code == 302 and r.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_settings_page_shows_and_saves(client, staff, app_settings):
    client.force_login(staff)
    r = client.get(reverse("settings"))
    html = r.content.decode()
    assert r.status_code == 200
    assert "map_logo.jpg" in html and app_settings.pdf_root_folder in html
    r = client.post(reverse("settings"), SETTINGS_POST)
    assert r.status_code == 302 and r.url == reverse("settings")
    s = AppSettings.load()
    assert s.attn_default == "UR DEPT" and s.pdf_root_folder == r"\\server\claims"
    assert s.template  # kept when no new file is uploaded
    assert "Settings saved" in client.get(reverse("settings")).content.decode()


@pytest.mark.django_db
def test_settings_page_rejects_bad_template(client, staff, app_settings, template_bytes):
    client.force_login(staff)
    bad = SimpleUploadedFile("bad.docx", _template_without(template_bytes, "keywords"))
    r = client.post(reverse("settings"), {**SETTINGS_POST, "template": bad})
    assert r.status_code == 200 and "policy_id" in r.content.decode()
    assert AppSettings.load().template_bytes() == template_bytes


@pytest.mark.django_db
def test_letter_page_shows_login_button_or_nav(client, staff, app_settings):
    html = client.get(reverse("letter_form")).content.decode()
    assert "Login" in html and "Logout" not in html
    client.force_login(staff)
    html = client.get(reverse("letter_form")).content.decode()
    assert "Logout" in html and reverse("settings") in html


@pytest.mark.django_db
def test_logout_redirects_to_letter_form(client, staff):
    client.force_login(staff)
    r = client.post(reverse("logout"))
    assert r.status_code == 302 and r.url == reverse("letter_form")


@pytest.mark.django_db
def test_admin_login_uses_branded_page(client):
    r = client.get("/admin/login/?next=/admin/letters/letter/")
    assert r.status_code == 302
    assert r.url == reverse("login") + "?next=/admin/letters/letter/"


@pytest.mark.django_db
def test_admin_pages_show_logo(client, staff):
    client.force_login(staff)
    assert "map_logo.jpg" in client.get("/admin/").content.decode()
