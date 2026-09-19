import datetime as dt
import json

import pytest
from django.urls import reverse
from django.utils import timezone

from letters.models import Handoff

DATA = {"case_encounter": "E-77", "policy_id": "WT-1", "member_name": "JOHN SMITH", "dob": "5/22/1953",
        "admission": "9/15/2026", "folder_name": "SMITH_JOHN", "user": "DOM\\rabdallah"}


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
    Handoff.objects.filter(token=token).update(created_at=timezone.now() - Handoff.TTL - dt.timedelta(seconds=1))
    r = client.get(reverse("letter_form"), {"t": token})
    assert "expired" in r.content.decode()


@pytest.mark.django_db
def test_handoff_create_purges_expired_rows():
    old = Handoff.create(DATA)
    Handoff.objects.filter(token=old).update(created_at=timezone.now() - Handoff.TTL - dt.timedelta(seconds=1))
    Handoff.create(DATA)
    assert not Handoff.objects.filter(token=old).exists()
    assert Handoff.objects.count() == 1
