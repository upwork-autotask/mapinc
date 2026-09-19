import datetime as dt

import pytest
from django.urls import reverse

from letters.models import Letter

VALID = {"case_encounter": "E1", "policy_id": "P1", "member_name": "JOHN SMITH", "dob": "1953-05-22",
         "admission": "9/15/2026", "folder_name": "SMITH", "user": "DOM\bob"}


@pytest.fixture(autouse=True)
def fake_converter(settings):
    settings.PDF_CONVERTER = "fake"


def _existing(**overrides):
    fields = dict(case_encounter="E1", policy_id="P1", member_name="OLD NAME", dob=dt.date(1953, 5, 22),
                  admission="9/1/2026", attn="a", client="c", doctor="d", folder_name="OLD",
                  pdf_path="", docx_path="", created_by="u", modified_by="u")
    return Letter.objects.create(**{**fields, **overrides})


@pytest.mark.django_db
def test_get_prefills_from_query_string(client, app_settings):
    r = client.get(reverse("letter_form"), {**VALID, "dob": "5/22/1953"})
    assert r.status_code == 200
    initial = r.context["form"].initial
    assert initial["member_name"] == "JOHN SMITH"
    assert initial["dob"] == dt.date(1953, 5, 22)
    assert initial["user"] == "DOM\bob"
    html = r.content.decode()
    assert 'value="1953-05-22"' in html
    assert app_settings.client_default in html and app_settings.doctor_default in html


@pytest.mark.django_db
def test_get_prefills_from_existing_letter_with_query_override(client, app_settings):
    _existing()
    r = client.get(reverse("letter_form"), {"case_encounter": "E1", "member_name": "NEW NAME"})
    initial = r.context["form"].initial
    assert initial["member_name"] == "NEW NAME"
    assert initial["policy_id"] == "P1"
    assert initial["folder_name"] == "OLD"
    assert initial["dob"] == dt.date(1953, 5, 22)


@pytest.mark.django_db
def test_get_without_parameters_shows_empty_form(client, app_settings):
    r = client.get(reverse("letter_form"))
    assert r.status_code == 200 and r.context["form"].initial == {}


@pytest.mark.django_db
def test_post_generates_and_shows_success(client, app_settings):
    r = client.post(reverse("letter_form"), VALID)
    assert r.status_code == 200
    assert "letters/success.html" in [t.name for t in r.templates]
    letter = Letter.objects.get(case_encounter="E1")
    assert letter.created_by == "DOM\bob"
    assert letter.pdf_path in r.content.decode()
    assert reverse("letter_pdf", args=["E1"]) in r.content.decode()


@pytest.mark.django_db
def test_post_missing_fields_shows_errors_and_saves_nothing(client, app_settings):
    r = client.post(reverse("letter_form"), {"case_encounter": "E1"})
    assert r.status_code == 200
    assert "member_name" in r.context["form"].errors
    assert Letter.objects.count() == 0


@pytest.mark.django_db
def test_post_pipeline_error_is_shown_in_message_bar(client, app_settings):
    app_settings.pdf_root_folder = ""
    app_settings.save()
    r = client.post(reverse("letter_form"), VALID)
    assert r.status_code == 200
    assert "root folder" in r.content.decode()
    assert Letter.objects.count() == 0


@pytest.mark.django_db
def test_pdf_download(client, app_settings):
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
