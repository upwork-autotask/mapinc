import pytest
from django.core.files.base import ContentFile

from letters.docgen import TEMPLATE_FIXTURE


@pytest.fixture
def template_bytes() -> bytes:
    return TEMPLATE_FIXTURE.read_bytes()


@pytest.fixture
def app_settings(db, tmp_path, template_bytes, settings):
    from letters.models import AppSettings

    settings.MEDIA_ROOT = tmp_path / "media"
    s = AppSettings.load()
    s.template.save("clinicals_request_template.docx", ContentFile(template_bytes), save=False)
    s.save()
    return s


@pytest.fixture
def claims_folder(tmp_path):
    """The full destination folder the launcher would pass in folder_name."""
    return tmp_path / "claims" / "SMITH_JOHN"
