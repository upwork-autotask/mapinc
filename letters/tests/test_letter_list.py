import datetime as dt

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from letters.models import Letter


@pytest.fixture
def staff(db):
    return User.objects.create_superuser("report", "report@example.com", "pw")


def _letter(i, **overrides):
    fields = dict(case_encounter=f"E-{i:03d}", policy_id=f"P-{i}", member_name=f"MEMBER {i}",
                  dob=dt.date(1970, 1, 1), admission="9/1/2026", attn="a", client="c", doctor="d",
                  folder_name=rf"D:\claims\M{i}", pdf_path=rf"D:\claims\M{i}\letter{i}.pdf", docx_path="",
                  created_by="alice", modified_by="bob")
    return Letter.objects.create(**{**fields, **overrides})


@pytest.mark.django_db
def test_list_requires_login(client):
    r = client.get(reverse("letter_list"))
    assert r.status_code == 302 and r.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_list_shows_letters_with_links(client, staff):
    _letter(1)
    client.force_login(staff)
    r = client.get(reverse("letter_list"))
    html = r.content.decode()
    assert r.status_code == 200
    assert "E-001" in html and "MEMBER 1" in html and "alice" in html and "bob" in html
    assert reverse("letter_pdf", args=["E-001"]) in html
    assert f"{reverse('letter_form')}?case_encounter=E-001" in html


@pytest.mark.django_db
def test_list_search_filters_on_case_policy_or_member(client, staff):
    _letter(1, member_name="JOHN SMITH")
    _letter(2, policy_id="WT-999")
    _letter(3)
    client.force_login(staff)
    for q, expected in (("smith", {"E-001"}), ("wt-999", {"E-002"}), ("E-00", {"E-001", "E-002", "E-003"})):
        r = client.get(reverse("letter_list"), {"q": q})
        shown = {l.case_encounter for l in r.context["page"].object_list}
        assert shown == expected, q


@pytest.mark.django_db
def test_list_is_paginated_newest_first(client, staff):
    for i in range(30):
        _letter(i)
    client.force_login(staff)
    r = client.get(reverse("letter_list"))
    page = r.context["page"]
    assert page.paginator.num_pages == 2 and len(page.object_list) == 25
    assert page.object_list[0].case_encounter == "E-029"  # most recently modified first
    r = client.get(reverse("letter_list"), {"page": 2})
    assert len(r.context["page"].object_list) == 5


@pytest.mark.django_db
def test_nav_links_to_the_list(client, staff):
    client.force_login(staff)
    assert reverse("letter_list") in client.get(reverse("letter_form")).content.decode()
