import datetime as dt

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from letters.models import AppSettings, AuditEvent, Letter

A = AuditEvent.Action
BASE = {"case_encounter": "E1", "policy_id": "P1", "member_name": "JOHN SMITH", "dob": "1953-05-22",
        "admission": "9/15/2026", "user": "DOM\\bob"}


@pytest.fixture
def VALID(claims_folder):
    return {**BASE, "folder_name": str(claims_folder)}


@pytest.fixture(autouse=True)
def fake_converter(settings):
    settings.PDF_CONVERTER = "fake"


@pytest.fixture
def staff(db):
    return User.objects.create_superuser("report", "report@example.com", "pw")


def _events(action=None):
    qs = AuditEvent.objects.order_by("at", "id")
    return list(qs.filter(action=action) if action else qs)


@pytest.mark.django_db
def test_opening_the_form_for_a_case_is_audited(client, app_settings):
    client.get(reverse("letter_form"), {"case_encounter": "E1", "member_name": "X", "user": "DOM\\bob"})
    (ev,) = _events(A.FORM_OPENED)
    assert ev.case_encounter == "E1" and ev.windows_user == "DOM\\bob" and ev.ip == "127.0.0.1"
    client.get(reverse("letter_form"))  # blank form: nothing to audit
    assert len(_events()) == 1


@pytest.mark.django_db
def test_create_update_and_download_are_audited(client, app_settings, VALID):
    client.post(reverse("letter_form"), VALID)
    client.post(reverse("letter_form"), {**VALID, "admission": "9/16/2026", "user": "DOM\\jane"})
    client.get(reverse("letter_pdf", args=["E1"]))
    actions = [(e.action, e.windows_user) for e in _events()]
    assert actions == [(A.LETTER_CREATED, "DOM\\bob"), (A.LETTER_UPDATED, "DOM\\jane"), (A.PDF_DOWNLOADED, "")]
    assert all(e.case_encounter == "E1" for e in _events())


@pytest.mark.django_db
def test_failed_generation_is_audited(client, app_settings, VALID):
    client.post(reverse("letter_form"), {**VALID, "folder_name": "SMITH"})  # not a full path
    (ev,) = _events(A.LETTER_FAILED)
    assert "full path" in ev.detail and ev.case_encounter == "E1"


@pytest.mark.django_db
def test_list_and_settings_are_audited(client, staff, app_settings):
    client.force_login(staff)
    client.get(reverse("letter_list"), {"q": "smith"})
    client.post(reverse("settings"), {"attn_default": "UR DEPT", "client_default": "WORLDTRIPS",
                                      "doctor_default": "RICHARD ABDALLAH",
                                      "pdf_filename_pattern": AppSettings.DEFAULT_FILENAME_PATTERN})
    listed, changed = _events(A.LIST_VIEWED)[0], _events(A.SETTINGS_CHANGED)[0]
    assert listed.user == "report" and "smith" in listed.detail
    assert changed.user == "report" and "attn_default" in changed.detail


@pytest.mark.django_db
def test_login_logout_and_failures_are_audited(client, staff):
    client.post(reverse("login"), {"username": "report", "password": "wrong"})
    client.post(reverse("login"), {"username": "report", "password": "pw"})
    client.post(reverse("logout"))
    assert [e.action for e in _events()] == [A.LOGIN_FAILED, A.LOGIN, A.LOGOUT]
    assert "report" in _events(A.LOGIN_FAILED)[0].detail
    assert _events(A.LOGIN)[0].user == "report"


@pytest.mark.django_db
def test_regenerate_action_is_audited(client, staff, app_settings, claims_folder):
    Letter.objects.create(case_encounter="E9", policy_id="P", member_name="M", dob=dt.date(1970, 1, 1),
                          admission="x", attn="a", client="c", doctor="d", folder_name=str(claims_folder),
                          pdf_path="", docx_path="", created_by="u", modified_by="u")
    client.force_login(staff)
    client.post(reverse("admin:letters_letter_changelist"),
                {"action": "regenerate_pdf", "_selected_action": [Letter.objects.get().pk]}, follow=True)
    (ev,) = _events(A.PDF_REGENERATED)
    assert ev.user == "report" and ev.case_encounter == "E9"


@pytest.mark.django_db
def test_audit_page_access(client, staff):
    r = client.get(reverse("audit_log"))
    assert r.status_code == 302 and r.url.startswith(reverse("login"))
    clerk = User.objects.create_user("clerk", password="pw")  # logged in but not staff
    client.force_login(clerk)
    assert client.get(reverse("audit_log")).status_code == 403
    client.force_login(staff)
    assert client.get(reverse("audit_log")).status_code == 200


@pytest.mark.django_db
def test_audit_page_filters_and_csv(client, staff, app_settings, VALID):
    client.post(reverse("letter_form"), VALID)
    client.post(reverse("letter_form"), {**VALID, "case_encounter": "E2"})
    client.force_login(staff)
    r = client.get(reverse("audit_log"), {"q": "E2"})
    rows = list(r.context["page"].object_list)
    assert {e.case_encounter for e in rows} == {"E2"}
    r = client.get(reverse("audit_log"), {"action": A.LETTER_CREATED})
    assert all(e.action == A.LETTER_CREATED for e in r.context["page"].object_list)
    today = timezone.localdate().isoformat()  # the app's timezone, not the machine's
    assert client.get(reverse("audit_log"), {"from": today, "to": today}).context["page"].paginator.count >= 2
    assert client.get(reverse("audit_log"), {"from": "2000-01-01", "to": "2000-01-02"}).context["page"].paginator.count == 0

    r = client.get(reverse("audit_log"), {"format": "csv", "q": "E1"})
    assert r.status_code == 200 and r["Content-Type"].startswith("text/csv")
    body = b"".join(r.streaming_content).decode()
    assert body.splitlines()[0] == "at,user,windows_user,ip,action,case_encounter,detail"
    assert "E1" in body and "E2" not in body


@pytest.mark.django_db
def test_settings_and_letters_pages_require_staff(client):
    clerk = User.objects.create_user("clerk", password="pw")
    client.force_login(clerk)
    assert client.get(reverse("settings")).status_code == 403
    assert client.get(reverse("letter_list")).status_code == 403
