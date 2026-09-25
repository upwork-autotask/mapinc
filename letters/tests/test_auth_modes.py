import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from letters.models import Letter

BASE = {"case_encounter": "E1", "policy_id": "P1", "member_name": "JOHN SMITH", "dob": "1953-05-22",
        "admission": "9/15/2026", "user": "DOM\\launcher"}


@pytest.fixture
def VALID(claims_folder):
    return {**BASE, "folder_name": str(claims_folder)}


@pytest.fixture(autouse=True)
def fake_converter(settings):
    settings.PDF_CONVERTER = "fake"


@pytest.fixture
def login_mode(settings):
    settings.MAPINC_AUTH_MODE = "login"


@pytest.fixture
def remote_user_mode(settings):
    settings.MAPINC_AUTH_MODE = "remote_user"
    settings.MIDDLEWARE = list(settings.MIDDLEWARE)
    idx = settings.MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1
    settings.MIDDLEWARE.insert(idx, "letters.middleware.WindowsUserMiddleware")
    settings.AUTHENTICATION_BACKENDS = ["letters.auth.WindowsUserBackend",
                                        "django.contrib.auth.backends.ModelBackend"]


# --- open (default) ----------------------------------------------------------

@pytest.mark.django_db
def test_open_mode_records_launcher_user(client, app_settings, VALID):
    client.post(reverse("letter_form"), VALID)
    assert Letter.objects.get().created_by == "DOM\\launcher"


@pytest.mark.django_db
def test_open_mode_prefers_the_logged_in_user_when_there_is_one(client, app_settings, VALID):
    client.force_login(User.objects.create_user("alice", password="pw"))
    client.post(reverse("letter_form"), VALID)
    assert Letter.objects.get().created_by == "alice"


# --- login -------------------------------------------------------------------

@pytest.mark.django_db
def test_login_mode_requires_login_for_form_and_pdf(client, app_settings, login_mode, VALID):
    r = client.get(reverse("letter_form"), {"case_encounter": "E1"})
    assert r.status_code == 302 and r.url.startswith(reverse("login"))
    r = client.post(reverse("letter_form"), VALID)
    assert r.status_code == 302 and Letter.objects.count() == 0
    r = client.get(reverse("letter_pdf", args=["E1"]))
    assert r.status_code == 302 and r.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_login_mode_uses_the_verified_user(client, app_settings, login_mode, VALID):
    client.force_login(User.objects.create_user("bob", password="pw"))
    r = client.post(reverse("letter_form"), VALID)
    assert r.status_code == 200
    assert Letter.objects.get().created_by == "bob"  # not the self-reported DOM\launcher


# --- remote_user (IIS Windows Authentication) --------------------------------

@pytest.mark.django_db
def test_remote_user_header_authenticates_and_creates_a_non_staff_user(app_settings, remote_user_mode, VALID):
    c = Client(HTTP_X_REMOTE_USER="MAP\\jdoe")
    r = c.get(reverse("letter_form"))
    assert r.status_code == 200
    user = User.objects.get(username="jdoe")
    assert user.is_staff is False and not user.has_usable_password()
    r = c.post(reverse("letter_form"), VALID)
    assert r.status_code == 200 and Letter.objects.get().created_by == "jdoe"


@pytest.mark.django_db
def test_remote_user_mode_without_header_is_not_authenticated(app_settings, remote_user_mode):
    r = Client().get(reverse("letter_form"))
    assert r.status_code == 302 and r.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_remote_user_cannot_reach_staff_pages_until_promoted(app_settings, remote_user_mode):
    c = Client(HTTP_X_REMOTE_USER="MAP\\jdoe")
    assert c.get(reverse("settings")).status_code == 403
    User.objects.filter(username="jdoe").update(is_staff=True)
    assert c.get(reverse("settings")).status_code == 200


@pytest.mark.django_db
def test_remote_user_mode_hides_login_and_logout_buttons(app_settings, remote_user_mode):
    html = Client(HTTP_X_REMOTE_USER="MAP\\jdoe").get(reverse("letter_form")).content.decode()
    assert "Logout" not in html and ">Login<" not in html
    assert "jdoe" in html  # signed-in name shown instead
