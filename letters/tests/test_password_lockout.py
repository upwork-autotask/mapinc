import pytest
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.urls import reverse

from letters.models import AuditEvent


@pytest.mark.parametrize("bad", ["Short1", "123456789012", "password1234"])
def test_weak_passwords_are_rejected(bad):
    with pytest.raises(ValidationError):
        validate_password(bad)


def test_password_similar_to_username_is_rejected():
    with pytest.raises(ValidationError):
        validate_password("clinicalsreport1", user=User(username="clinicalsreport"))


def test_strong_password_is_accepted():
    validate_password("Clinicals-Request-2026!", user=User(username="report"))


@pytest.mark.django_db
def test_account_locks_after_five_failures_and_is_audited(client):
    User.objects.create_user("report", password="Clinicals-Request-2026!")
    for _ in range(4):
        r = client.post(reverse("login"), {"username": "report", "password": "wrong"})
        assert r.status_code == 200  # still just "try again"
    r = client.post(reverse("login"), {"username": "report", "password": "wrong"})
    assert r.status_code == 429  # fifth failure locks the account
    # the RIGHT password is refused while locked
    r = client.post(reverse("login"), {"username": "report", "password": "Clinicals-Request-2026!"})
    assert r.status_code == 429 and "locked" in r.content.decode().lower()
    assert AuditEvent.objects.filter(action=AuditEvent.Action.LOCKOUT, detail__contains="report").exists()


@pytest.mark.django_db
def test_other_accounts_are_not_affected_by_a_lockout(client):
    User.objects.create_user("report", password="Clinicals-Request-2026!")
    User.objects.create_user("other", password="Another-Strong-Pass-99")
    for _ in range(5):
        client.post(reverse("login"), {"username": "report", "password": "wrong"})
    r = client.post(reverse("login"), {"username": "other", "password": "Another-Strong-Pass-99"})
    assert r.status_code == 302
