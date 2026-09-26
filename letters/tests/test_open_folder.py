import datetime as dt

import pytest
from django.urls import reverse

from letters.models import Letter


@pytest.fixture
def opened(monkeypatch):
    """Record what would have been handed to Windows Explorer."""
    calls = []

    def fake(folder):
        calls.append(str(folder))
        return True

    monkeypatch.setattr("letters.views.open_in_explorer", fake)
    return calls


@pytest.fixture
def letter(db, claims_folder):
    claims_folder.mkdir(parents=True, exist_ok=True)
    return Letter.objects.create(
        case_encounter="E1", policy_id="P1", member_name="JOHN SMITH", dob=dt.date(1953, 5, 22),
        admission="9/15/2026", attn="a", client="c", doctor="d", folder_name=str(claims_folder),
        pdf_path="", docx_path="", created_by="u", modified_by="u")


@pytest.mark.django_db
def test_opens_the_folder_when_the_browser_is_on_the_server(client, letter, opened, claims_folder):
    r = client.post(reverse("open_folder"), {"case_encounter": "E1"}, REMOTE_ADDR="127.0.0.1")
    assert r.status_code == 200 and r.json()["opened"] is True
    assert opened == [str(claims_folder)]


@pytest.mark.django_db
def test_uses_the_posted_path_when_the_letter_does_not_exist_yet(client, opened, tmp_path):
    folder = tmp_path / "claims" / "NEW_CASE"
    folder.mkdir(parents=True)
    r = client.post(reverse("open_folder"), {"case_encounter": "NEW", "path": str(folder)},
                    REMOTE_ADDR="127.0.0.1")
    assert r.json()["opened"] is True and opened == [str(folder)]


@pytest.mark.django_db
def test_a_remote_browser_is_told_to_fall_back(client, letter, opened):
    r = client.post(reverse("open_folder"), {"case_encounter": "E1"}, REMOTE_ADDR="192.168.1.50")
    assert r.status_code == 200
    assert r.json() == {"opened": False, "reason": "remote"}
    assert opened == []


@pytest.mark.django_db
def test_can_be_switched_off(client, letter, opened, settings):
    settings.MAPINC_LOCAL_EXPLORER = False
    r = client.post(reverse("open_folder"), {"case_encounter": "E1"}, REMOTE_ADDR="127.0.0.1")
    assert r.json() == {"opened": False, "reason": "disabled"} and opened == []


@pytest.mark.django_db
def test_a_folder_that_is_not_there_yet_is_reported(client, letter, opened, claims_folder):
    claims_folder.rmdir()
    r = client.post(reverse("open_folder"), {"case_encounter": "E1"}, REMOTE_ADDR="127.0.0.1")
    assert r.status_code == 404 and r.json()["opened"] is False
    assert "does not exist" in r.json()["reason"] and opened == []


@pytest.mark.django_db
def test_a_path_that_is_not_a_full_windows_path_is_refused(client, opened):
    r = client.post(reverse("open_folder"), {"case_encounter": "NEW", "path": "SMITH"},
                    REMOTE_ADDR="127.0.0.1")
    assert r.status_code == 400 and opened == []


@pytest.mark.django_db
def test_a_path_outside_the_allowed_roots_is_refused(client, opened, settings, tmp_path):
    settings.MAPINC_ALLOWED_FOLDER_ROOTS = [str(tmp_path / "claims")]
    r = client.post(reverse("open_folder"), {"case_encounter": "NEW", "path": r"C:\Windows"},
                    REMOTE_ADDR="127.0.0.1")
    assert r.status_code == 400 and opened == []


@pytest.mark.django_db
def test_get_is_not_allowed(client):
    assert client.get(reverse("open_folder")).status_code == 405
