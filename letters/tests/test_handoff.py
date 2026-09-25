import datetime as dt
import json

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from letters.models import Handoff, Letter

DATA = {"case_encounter": "E-77", "policy_id": "WT-1", "member_name": "JOHN SMITH", "dob": "5/22/1953",
        "admission": "9/15/2026", "folder_name": r"D:\claims\SMITH_JOHN", "user": "DOM\\rabdallah"}


@pytest.mark.django_db
def test_handoff_post_returns_a_link_without_the_data(client):
    r = client.post(reverse("letter_handoff"), DATA)
    assert r.status_code == 200 and r["Content-Type"].startswith("text/plain")
    url = r.content.decode().strip()
    assert url.startswith("http://testserver/letter/?t=")
    assert "SMITH" not in url and "WT-1" not in url
    assert Handoff.objects.get().data["member_name"] == "JOHN SMITH"


@pytest.mark.django_db
def test_handoff_accepts_json(client):
    r = client.post(reverse("letter_handoff"), json.dumps(DATA), content_type="application/json")
    assert r.status_code == 200 and "?t=" in r.content.decode()


@pytest.mark.django_db
def test_handoff_rejects_get(client):
    assert client.get(reverse("letter_handoff")).status_code == 405


@pytest.mark.django_db
def test_form_prefills_from_handoff_token(client, app_settings):
    url = client.post(reverse("letter_handoff"), DATA).content.decode().strip()
    r = client.get(url)
    initial = r.context["form"].initial
    assert initial["case_encounter"] == "E-77"
    assert initial["member_name"] == "JOHN SMITH"
    assert initial["dob"] == dt.date(1953, 5, 22)
    assert initial["user"] == "DOM\\rabdallah"
    # the link is reusable until it expires (page refresh / Edit again)
    assert client.get(url).context["form"].initial["member_name"] == "JOHN SMITH"


@pytest.mark.django_db
def test_query_string_still_overrides_handoff(client, app_settings):
    url = client.post(reverse("letter_handoff"), DATA).content.decode().strip()
    r = client.get(url + "&member_name=JANE+DOE")
    assert r.context["form"].initial["member_name"] == "JANE DOE"
    assert r.context["form"].initial["policy_id"] == "WT-1"


@pytest.mark.django_db
def test_expired_or_unknown_token_shows_message(client, app_settings):
    r = client.get(reverse("letter_form"), {"t": "nope"})
    assert r.status_code == 200 and "expired" in r.content.decode()
    assert r.context["form"].initial == {}

    token = Handoff.create(DATA)
    Handoff.objects.filter(token=token).update(created_at=timezone.now() - Handoff.ttl() - dt.timedelta(seconds=1))
    r = client.get(reverse("letter_form"), {"t": token})
    assert "expired" in r.content.decode()


@pytest.mark.django_db
def test_handoff_create_purges_expired_rows():
    old = Handoff.create(DATA)
    Handoff.objects.filter(token=old).update(created_at=timezone.now() - Handoff.ttl() - dt.timedelta(seconds=1))
    Handoff.create(DATA)
    assert not Handoff.objects.filter(token=old).exists()
    assert Handoff.objects.count() == 1


@pytest.mark.django_db
def test_ttl_comes_from_settings(settings):
    settings.MAPINC_HANDOFF_MINUTES = 7
    assert Handoff.ttl() == dt.timedelta(minutes=7)


@pytest.mark.django_db
def test_token_is_single_use_after_the_letter_is_saved(client, app_settings, settings, claims_folder):
    settings.PDF_CONVERTER = "fake"
    url = client.post(reverse("letter_handoff"), DATA).content.decode().strip()
    r = client.get(url)
    token = r.context["form"].initial["token"]
    assert token and Handoff.objects.filter(token=token).exists()
    r = client.post(reverse("letter_form"),
                    {**DATA, "dob": "1953-05-22", "folder_name": str(claims_folder), "token": token})
    assert r.status_code == 200 and Letter.objects.filter(case_encounter="E-77").exists()
    assert not Handoff.objects.filter(token=token).exists()
    assert "expired" in client.get(url).content.decode()


@pytest.mark.django_db
def test_handoff_endpoint_restricted_to_allowed_networks(client, settings):
    settings.MAPINC_HANDOFF_ALLOWED_NETWORKS = ["10.20.0.0/16", "127.0.0.1/32"]
    assert client.post(reverse("letter_handoff"), DATA, REMOTE_ADDR="10.20.5.9").status_code == 200
    assert client.post(reverse("letter_handoff"), DATA, REMOTE_ADDR="127.0.0.1").status_code == 200
    assert client.post(reverse("letter_handoff"), DATA, REMOTE_ADDR="192.168.9.9").status_code == 403


@pytest.mark.django_db
def test_query_prefill_can_be_disabled(client, app_settings, settings):
    settings.MAPINC_ALLOW_QUERY_PREFILL = False
    r = client.get(reverse("letter_form"), DATA)
    initial = r.context["form"].initial
    assert initial.get("case_encounter") == "E-77" and initial.get("user") == "DOM\\rabdallah"
    assert "member_name" not in initial and "dob" not in initial
    # handoff tokens still work
    url = client.post(reverse("letter_handoff"), DATA).content.decode().strip()
    assert client.get(url).context["form"].initial["member_name"] == "JOHN SMITH"


@pytest.mark.django_db
def test_purge_handoffs_command():
    fresh = Handoff.create(DATA)
    stale = Handoff.create(DATA)
    Handoff.objects.filter(token=stale).update(created_at=timezone.now() - Handoff.ttl() - dt.timedelta(seconds=1))
    call_command("purge_handoffs")
    assert Handoff.objects.filter(token=fresh).exists()
    assert not Handoff.objects.filter(token=stale).exists()


@pytest.mark.django_db
def test_handoff_carries_the_extra_case_fields(client, app_settings):
    url = client.post(reverse("letter_handoff"),
                      {**DATA, "case_location": "MIAMI", "case_type": "INPATIENT"}).content.decode().strip()
    initial = client.get(url).context["form"].initial
    assert initial["case_location"] == "MIAMI" and initial["case_type"] == "INPATIENT"
    assert "MIAMI" not in url
