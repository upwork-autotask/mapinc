# Clinicals Request Letter Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Django app, opened from MS Access via a query-string URL, that shows an Access-styled form, fills the "Clinicals Request" Word template, exports a PDF with Word into a per-case folder, and records each letter in PostgreSQL with an audit trail.

**Architecture:** One Django project `mapinc` with one app `letters`. Three pure units under `letters/docgen/` do the work — `template_fill` (rewrites the content controls in the `.docx` with lxml), `pdf_convert` (Word COM behind a tiny interface with a `fake` implementation for tests) and `service.generate_letter` (orchestration + upsert). Views are thin. Django admin manages the singleton `AppSettings`, the template file and letter history. Connection settings come from `mapinc.ini`.

**Tech Stack:** Python 3.13, Django 5.2 LTS, PostgreSQL 18, psycopg 3, lxml, pywin32, waitress, pytest + pytest-django.

**Spec:** `docs/superpowers/specs/2026-09-19-clinicals-letter-design.md`

## Global Constraints

- Repo root is `C:\Users\bhanu\Documents\Upwork\2026\Sept\Richard\mapinc`; all paths below are relative to it. Run commands from PowerShell in that directory with the venv active (`.venv\Scripts\Activate.ps1`).
- Python **3.13** via `py -3.13`; Django pinned `>=5.2,<5.3` (LTS).
- Database: PostgreSQL, role `mapinc` / password `mapinc` / database `mapinc` on `localhost:5432` for development. The role needs `CREATEDB` so pytest-django can create `test_mapinc`.
- Config file `mapinc.ini` is **never committed**; `mapinc.ini.example` is.
- The letter key is `case_encounter` (unique). Query-string names are exactly: `case_encounter, policy_id, member_name, dob, admission, folder_name, user`.
- Field → content-control mapping (by last element of the binding xpath): `keywords→policy_id, category→member_name, PublishDate→dob, contentStatus→admission, Abstract→attn, Company→client, creator→doctor`. `subject` is left untouched.
- Dates on the letter render as `M/d/yyyy` (no leading zeros, e.g. `5/22/1953`).
- Default filename pattern: `CLINICALS REQUEST-{member_name}-SENT{MMDDYY}.pdf`.
- Audit user comes from the `user` parameter; missing → `"unknown"`.
- TDD: write the failing test first, run it, implement, run again, commit. Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
- Test command everywhere: `pytest -q` (config in `pytest.ini`). Word-dependent tests are marked `@pytest.mark.word` and skipped unless `WINWORD.EXE` exists.

## File Structure

```
mapinc/
  .gitignore  README.md  requirements.txt  pytest.ini  run.bat  mapinc.ini.example  manage.py
  mapinc/                      Django project package
    __init__.py  settings.py (reads mapinc.ini)  urls.py  wsgi.py  asgi.py
  letters/
    __init__.py  apps.py  models.py  forms.py  views.py  admin.py  urls.py
    migrations/
    fixtures/clinicals_request_template.docx      the real template, used by tests and the loader command
    management/commands/load_default_template.py  copies the fixture into AppSettings.template
    docgen/__init__.py  template_fill.py  pdf_convert.py  service.py  filenames.py
    templates/letters/form.html  success.html
    static/letters/access.css
    tests/__init__.py  conftest.py  test_template_fill.py  test_pdf_convert.py
          test_filenames.py  test_service.py  test_views.py  test_admin.py  test_settings_ini.py
  access/LetterLauncher.bas
  docs/superpowers/specs/…  docs/superpowers/plans/…
```

Responsibilities: `template_fill.py` knows only about the docx XML; `pdf_convert.py` knows only about turning a `.docx` path into a `.pdf` path; `filenames.py` builds safe filenames from the pattern; `service.py` is the only module that touches both the filesystem layout and the `Letter` model; `views.py`/`forms.py` handle HTTP only.

---

### Task 1: Local PostgreSQL, virtualenv, and Django skeleton that boots from `mapinc.ini`

**Files:**
- Create: `.gitignore`, `requirements.txt`, `pytest.ini`, `mapinc.ini.example`, `mapinc.ini` (uncommitted), `manage.py`, `mapinc/__init__.py`, `mapinc/settings.py`, `mapinc/urls.py`, `mapinc/wsgi.py`, `mapinc/asgi.py`, `letters/__init__.py`, `letters/apps.py`, `letters/tests/__init__.py`, `letters/tests/test_settings_ini.py`

**Interfaces:**
- Produces: `settings.MAPINC_CONFIG` (a `configparser.ConfigParser`), `settings.PDF_CONVERTER: str`, `settings.WORD_TIMEOUT_SECONDS: int`, `settings.MEDIA_ROOT`, and the `letters` app registered in `INSTALLED_APPS`.

- [ ] **Step 1: Install PostgreSQL 18 (needs a UAC prompt — approve it)**

Run in PowerShell:
```powershell
winget install --id PostgreSQL.PostgreSQL.18 --source winget --accept-package-agreements --accept-source-agreements --override "--mode unattended --unattendedmodeui none --superpassword postgres --serverport 5432"
```
Expected: exit code 0; service `postgresql-x64-18` running (`Get-Service postgresql-x64-18`). If `winget` cannot elevate, run the same command from an elevated PowerShell.

- [ ] **Step 2: Create the role and database**

```powershell
$env:PGPASSWORD = "postgres"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -c "CREATE ROLE mapinc LOGIN PASSWORD 'mapinc' CREATEDB;"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -c "CREATE DATABASE mapinc OWNER mapinc;"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U mapinc -h localhost -d mapinc -c "select current_user, current_database();"
```
Expected: last command prints `mapinc | mapinc`.

- [ ] **Step 3: Create the virtualenv and requirements**

`requirements.txt`:
```
Django>=5.2,<5.3
psycopg[binary]>=3.2,<4
lxml>=5.3
pywin32>=308; sys_platform == "win32"
waitress>=3.0
pytest>=8
pytest-django>=4.9
```
```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -c "import django, psycopg, lxml, win32com; print(django.get_version())"
```
Expected: prints `5.2.x`.

- [ ] **Step 4: `.gitignore`, `pytest.ini`, `mapinc.ini.example`, `mapinc.ini`**

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
mapinc.ini
media/
staticfiles/
.pytest_cache/
*.log
```
`pytest.ini`:
```ini
[pytest]
DJANGO_SETTINGS_MODULE = mapinc.settings
python_files = test_*.py
testpaths = letters/tests
markers =
    word: requires Microsoft Word (skipped when WINWORD.EXE is absent)
```
`mapinc.ini.example` (copy it to `mapinc.ini` unchanged for development):
```ini
[database]
host = localhost
port = 5432
name = mapinc
user = mapinc
password = mapinc

[app]
secret_key = change-me-to-a-long-random-string
allowed_hosts = *
debug = true
pdf_converter = word
word_timeout_seconds = 60
```
```powershell
Copy-Item mapinc.ini.example mapinc.ini
```

- [ ] **Step 5: Write the failing settings test**

`letters/tests/__init__.py`: empty file.

`letters/tests/test_settings_ini.py`:
```python
from django.conf import settings


def test_database_comes_from_ini():
    db = settings.DATABASES["default"]
    assert db["ENGINE"] == "django.db.backends.postgresql"
    assert db["NAME"] == settings.MAPINC_CONFIG["database"]["name"]
    assert db["HOST"] == settings.MAPINC_CONFIG["database"]["host"]


def test_app_settings_come_from_ini():
    assert settings.PDF_CONVERTER in {"word", "libreoffice", "fake"}
    assert isinstance(settings.WORD_TIMEOUT_SECONDS, int)
    assert "letters" in settings.INSTALLED_APPS
```

- [ ] **Step 6: Run it to verify it fails**

Run: `pytest -q`
Expected: errors — `ModuleNotFoundError: No module named 'mapinc.settings'` (or similar) because the project does not exist yet.

- [ ] **Step 7: Create the project skeleton**

```powershell
django-admin startproject mapinc .
python manage.py startapp letters
```
Delete the generated `letters/tests.py` (the `letters/tests/` package replaces it) and `letters/views.py` content can stay as-is for now.

Replace `mapinc/settings.py` entirely with:
```python
"""
Django settings for mapinc. All environment-specific values come from
mapinc.ini next to manage.py (see mapinc.ini.example).
"""
import configparser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_INI_PATH = BASE_DIR / "mapinc.ini"
if not _INI_PATH.exists():
    raise RuntimeError(
        f"Missing {_INI_PATH}. Copy mapinc.ini.example to mapinc.ini and edit it."
    )
MAPINC_CONFIG = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
MAPINC_CONFIG.read(_INI_PATH, encoding="utf-8")

_db = MAPINC_CONFIG["database"]
_app = MAPINC_CONFIG["app"]

SECRET_KEY = _app.get("secret_key", "change-me")
DEBUG = _app.getboolean("debug", fallback=False)
ALLOWED_HOSTS = [h.strip() for h in _app.get("allowed_hosts", "*").split(",") if h.strip()]

PDF_CONVERTER = _app.get("pdf_converter", "word").strip().lower()
WORD_TIMEOUT_SECONDS = _app.getint("word_timeout_seconds", fallback=60)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "letters",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "mapinc.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "mapinc.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _db.get("name", "mapinc"),
        "USER": _db.get("user", "mapinc"),
        "PASSWORD": _db.get("password", ""),
        "HOST": _db.get("host", "localhost"),
        "PORT": _db.get("port", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/New_York"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
```

- [ ] **Step 8: Run the tests and Django's checks**

Run: `pytest -q` then `python manage.py check`
Expected: `2 passed`; `System check identified no issues`.

- [ ] **Step 9: Commit**

```powershell
git add .gitignore requirements.txt pytest.ini mapinc.ini.example manage.py mapinc letters
git commit -m "Scaffold Django project reading mapinc.ini, with PostgreSQL dev database

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```
Verify `git status` does not list `mapinc.ini`.

---
### Task 2: Models (`Letter`, `AppSettings`), migrations, template fixture and loader command

**Files:**
- Create: `letters/models.py` (replace generated), `letters/migrations/0001_initial.py` (generated), `letters/fixtures/clinicals_request_template.docx`, `letters/management/__init__.py`, `letters/management/commands/__init__.py`, `letters/management/commands/load_default_template.py`, `letters/tests/conftest.py`, `letters/tests/test_models.py`

**Interfaces:**
- Produces:
  - `Letter` model with fields exactly: `case_encounter, policy_id, member_name, dob, admission, attn, client, doctor, folder_name, pdf_path, docx_path, created_by, created_at, modified_by, modified_at`.
  - `AppSettings` model with `attn_default, client_default, doctor_default, pdf_root_folder, pdf_filename_pattern, template` and classmethod `AppSettings.load() -> AppSettings` (creates the singleton row with defaults if absent).
  - `AppSettings.DEFAULT_FILENAME_PATTERN = "CLINICALS REQUEST-{member_name}-SENT{MMDDYY}.pdf"`.
  - `AppSettings.template_bytes() -> bytes` (reads the uploaded template).
  - Management command `load_default_template` and `TEMPLATE_FIXTURE: Path` in `letters/docgen/__init__.py`.
  - pytest fixtures `app_settings` (AppSettings row with template loaded, `pdf_root_folder` = a tmp dir) and `template_bytes`.

- [ ] **Step 1: Copy the real template into the repo**

```powershell
New-Item -ItemType Directory -Force letters\fixtures | Out-Null
Copy-Item "..\FAX TEMPLATE-CLINICALS REQUESTS- PT NAME-SENTXXXXXX.docx" letters\fixtures\clinicals_request_template.docx
```

`letters/docgen/__init__.py`:
```python
from pathlib import Path

TEMPLATE_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "clinicals_request_template.docx"
```

- [ ] **Step 2: Write the failing model tests**

`letters/tests/conftest.py`:
```python
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
    s.pdf_root_folder = str(tmp_path / "claims")
    s.template.save("clinicals_request_template.docx", ContentFile(template_bytes), save=False)
    s.save()
    return s
```

`letters/tests/test_models.py`:
```python
import pytest
from django.db import IntegrityError

from letters.models import AppSettings, Letter


@pytest.mark.django_db
def test_app_settings_load_creates_singleton_with_defaults():
    s = AppSettings.load()
    assert s.pk == 1
    assert s.attn_default == "UR DEPARTMENT"
    assert s.client_default == "WORLDTRIPS"
    assert s.doctor_default == "RICHARD ABDALLAH"
    assert s.pdf_filename_pattern == AppSettings.DEFAULT_FILENAME_PATTERN
    assert AppSettings.load().pk == 1
    assert AppSettings.objects.count() == 1


@pytest.mark.django_db
def test_app_settings_template_bytes(app_settings, template_bytes):
    assert app_settings.template_bytes() == template_bytes


@pytest.mark.django_db
def test_letter_case_encounter_is_unique():
    Letter.objects.create(case_encounter="E1", policy_id="P1", member_name="A", dob="1953-05-22",
                          admission="9/15/2026", attn="x", client="y", doctor="z",
                          folder_name="F", pdf_path="", docx_path="",
                          created_by="u", modified_by="u")
    with pytest.raises(IntegrityError):
        Letter.objects.create(case_encounter="E1", policy_id="P2", member_name="B", dob="1953-05-22",
                              admission="", attn="x", client="y", doctor="z",
                              folder_name="F", pdf_path="", docx_path="",
                              created_by="u", modified_by="u")


@pytest.mark.django_db
def test_letter_timestamps_are_set_automatically():
    letter = Letter.objects.create(case_encounter="E2", policy_id="P1", member_name="A", dob="1953-05-22",
                                   admission="", attn="x", client="y", doctor="z",
                                   folder_name="F", pdf_path="", docx_path="",
                                   created_by="u", modified_by="u")
    assert letter.created_at is not None and letter.modified_at is not None
```

- [ ] **Step 3: Run to verify failure**

Run: `pytest -q letters/tests/test_models.py`
Expected: `ImportError: cannot import name 'AppSettings'`.

- [ ] **Step 4: Implement the models**

`letters/models.py`:
```python
from django.db import models


class AppSettings(models.Model):
    """Single-row table edited in admin. Always access it via AppSettings.load()."""

    DEFAULT_FILENAME_PATTERN = "CLINICALS REQUEST-{member_name}-SENT{MMDDYY}.pdf"

    attn_default = models.CharField("ATTN default", max_length=200, default="UR DEPARTMENT")
    client_default = models.CharField("Client default", max_length=200, default="WORLDTRIPS")
    doctor_default = models.CharField("Doctor default", max_length=200, default="RICHARD ABDALLAH",
                                      help_text='Printed after "Dr." in the letter.')
    pdf_root_folder = models.CharField(
        "PDF root folder", max_length=500, blank=True,
        help_text=r"Local or UNC path, e.g. \\server\claims. Access passes the sub-folder name.")
    pdf_filename_pattern = models.CharField(
        "PDF filename pattern", max_length=200, default=DEFAULT_FILENAME_PATTERN,
        help_text="Placeholders: {member_name} {policy_id} {case_encounter} {MMDDYY} {YYYYMMDD}")
    template = models.FileField("Word template (.docx)", upload_to="templates/", blank=True)

    class Meta:
        verbose_name = "Settings"
        verbose_name_plural = "Settings"

    def __str__(self):
        return "Application settings"

    @classmethod
    def load(cls) -> "AppSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce the singleton
        super().save(*args, **kwargs)

    def template_bytes(self) -> bytes:
        if not self.template:
            raise ValueError("No Word template uploaded. Set it in admin > Settings.")
        with self.template.open("rb") as fh:
            return fh.read()


class Letter(models.Model):
    """One generated Clinicals Request letter per case/encounter."""

    case_encounter = models.CharField("Case/Encounter", max_length=100, unique=True)
    policy_id = models.CharField("Policy ID", max_length=100)
    member_name = models.CharField(max_length=200)
    dob = models.DateField("Date of birth")
    admission = models.CharField(max_length=200)
    # snapshot of the defaults used at generation time
    attn = models.CharField(max_length=200)
    client = models.CharField(max_length=200)
    doctor = models.CharField(max_length=200)
    folder_name = models.CharField(max_length=300)
    pdf_path = models.CharField(max_length=1000, blank=True)
    docx_path = models.CharField(max_length=1000, blank=True)
    created_by = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_by = models.CharField(max_length=150)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-modified_at"]

    def __str__(self):
        return f"{self.case_encounter} – {self.member_name}"
```

```powershell
python manage.py makemigrations letters
python manage.py migrate
```
Expected: `letters/migrations/0001_initial.py` created; migrate applies cleanly against the local `mapinc` database.

- [ ] **Step 5: Run the model tests**

Run: `pytest -q letters/tests/test_models.py`
Expected: `4 passed`.

- [ ] **Step 6: Write the failing loader-command test**

Append to `letters/tests/test_models.py`:
```python
from django.core.management import call_command


@pytest.mark.django_db
def test_load_default_template_command(settings, tmp_path, template_bytes):
    settings.MEDIA_ROOT = tmp_path / "media"
    call_command("load_default_template")
    assert AppSettings.load().template_bytes() == template_bytes
    # running twice replaces rather than duplicates
    call_command("load_default_template")
    assert AppSettings.objects.count() == 1
```

Run: `pytest -q letters/tests/test_models.py::test_load_default_template_command`
Expected: FAIL — `Unknown command: 'load_default_template'`.

- [ ] **Step 7: Implement the command**

`letters/management/__init__.py` and `letters/management/commands/__init__.py`: empty files.

`letters/management/commands/load_default_template.py`:
```python
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from letters.docgen import TEMPLATE_FIXTURE
from letters.models import AppSettings


class Command(BaseCommand):
    help = "Load the bundled Clinicals Request .docx into Settings > template."

    def handle(self, *args, **options):
        s = AppSettings.load()
        if s.template:
            s.template.delete(save=False)
        s.template.save(TEMPLATE_FIXTURE.name, ContentFile(TEMPLATE_FIXTURE.read_bytes()), save=False)
        s.save()
        self.stdout.write(self.style.SUCCESS(f"Template loaded: {s.template.name}"))
```

- [ ] **Step 8: Run all tests**

Run: `pytest -q`
Expected: all pass (7 tests).

- [ ] **Step 9: Commit**

```powershell
git add letters
git commit -m "Add Letter and AppSettings models, template fixture and loader command

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---
### Task 3: `template_fill.py` — fill the Word content controls and document properties

**Files:**
- Create: `letters/docgen/template_fill.py`, `letters/tests/test_template_fill.py`

**Interfaces:**
- Consumes: `template_bytes` fixture (Task 2).
- Produces:
  - `fill_template(template_bytes: bytes, values: dict) -> bytes` — `values` keys are the field names `policy_id, member_name, dob (datetime.date), admission, attn, client, doctor`; missing keys leave that control untouched; `dob` that is not a `date` raises `TypeError`.
  - `format_date(d: date) -> str` (`M/d/yyyy`), `binding_name(xpath: str) -> str | None`, `FIELD_BINDINGS: dict[str, str]`.

- [ ] **Step 1: Write the failing tests**

`letters/tests/test_template_fill.py`:
```python
import datetime as dt
import io
import zipfile

import pytest
from lxml import etree

from letters.docgen.template_fill import FIELD_BINDINGS, binding_name, fill_template, format_date

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
CHANGED_PARTS = {"word/document.xml", "docProps/core.xml", "docProps/app.xml", "customXml/item1.xml"}

SAMPLE = dict(
    policy_id="WT-123456",
    member_name="JOHN SMITH",
    dob=dt.date(1953, 5, 22),
    admission="9/15/2026",
    attn="UR DEPARTMENT",
    client="WORLDTRIPS",
    doctor="RICHARD ABDALLAH",
)


def _sdt_texts(docx_bytes: bytes) -> dict[str, list[str]]:
    """Map binding name -> text of every content control bound to it, in document order."""
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(docx_bytes)).read("word/document.xml"))
    out: dict[str, list[str]] = {}
    for sdt in root.iter(f"{{{W}}}sdt"):
        binding = sdt.find("w:sdtPr/w:dataBinding", NS)
        if binding is None:
            continue
        name = binding_name(binding.get(f"{{{W}}}xpath"))
        text = "".join(t.text or "" for t in sdt.iter(f"{{{W}}}t"))
        out.setdefault(name, []).append(text)
    return out


def test_binding_name_takes_last_xpath_element():
    assert binding_name("/ns1:coreProperties[1]/ns1:keywords[1]") == "keywords"
    assert binding_name("/ns0:CoverPageProperties[1]/ns0:PublishDate[1]") == "PublishDate"
    assert binding_name("") is None


def test_format_date_has_no_leading_zeros():
    assert format_date(dt.date(1953, 5, 22)) == "5/22/1953"
    assert format_date(dt.date(2026, 12, 1)) == "12/1/2026"


def test_template_contains_every_expected_binding(template_bytes):
    assert set(FIELD_BINDINGS) <= set(_sdt_texts(template_bytes))


def test_fills_every_bound_control_including_duplicates(template_bytes):
    texts = _sdt_texts(fill_template(template_bytes, SAMPLE))
    assert texts["keywords"] == ["WT-123456"]
    assert texts["category"] == ["JOHN SMITH", "JOHN SMITH"]
    assert texts["PublishDate"] == ["5/22/1953"]
    assert texts["contentStatus"] == ["9/15/2026", "9/15/2026"]
    assert texts["Abstract"] == ["UR DEPARTMENT"]
    assert texts["Company"] == ["WORLDTRIPS", "WORLDTRIPS"]
    assert texts["creator"] == ["RICHARD ABDALLAH", "RICHARD ABDALLAH"]
    assert texts["subject"] == ["CLINICALS REQUEST"]  # untouched


def test_placeholder_markers_removed_from_filled_controls(template_bytes):
    root = etree.fromstring(
        zipfile.ZipFile(io.BytesIO(fill_template(template_bytes, SAMPLE))).read("word/document.xml"))
    assert root.find(".//w:showingPlcHdr", NS) is None
    assert root.find(".//w:sdt//w:rStyle[@w:val='PlaceholderText']", NS) is None
    date_ctl = root.find(".//w:sdt/w:sdtPr/w:date", NS)
    assert date_ctl.get(f"{{{W}}}fullDate") == "1953-05-22T00:00:00Z"


def test_document_properties_updated(template_bytes):
    z = zipfile.ZipFile(io.BytesIO(fill_template(template_bytes, SAMPLE)))
    core = z.read("docProps/core.xml").decode()
    app = z.read("docProps/app.xml").decode()
    cover = z.read("customXml/item1.xml").decode()
    assert "<cp:keywords>WT-123456</cp:keywords>" in core
    assert "<cp:category>JOHN SMITH</cp:category>" in core
    assert "<cp:contentStatus>9/15/2026</cp:contentStatus>" in core
    assert "<dc:creator>RICHARD ABDALLAH</dc:creator>" in core
    assert "<Company>WORLDTRIPS</Company>" in app
    assert "<Abstract>UR DEPARTMENT</Abstract>" in cover
    assert "<PublishDate>1953-05-22T00:00:00Z</PublishDate>" in cover


def test_untouched_parts_are_byte_identical(template_bytes):
    src = zipfile.ZipFile(io.BytesIO(template_bytes))
    out = zipfile.ZipFile(io.BytesIO(fill_template(template_bytes, SAMPLE)))
    assert src.namelist() == out.namelist()
    for name in src.namelist():
        if name not in CHANGED_PARTS:
            assert src.read(name) == out.read(name), name
    assert out.testzip() is None


def test_missing_values_leave_controls_alone(template_bytes):
    texts = _sdt_texts(fill_template(template_bytes, {"policy_id": "X"}))
    assert texts["keywords"] == ["X"]
    assert texts["Company"] == ["WORLDTRIPS", "WORLDTRIPS"]
    assert texts["category"] == ["[Category]", "[Category]"]


def test_dob_must_be_a_date(template_bytes):
    with pytest.raises(TypeError):
        fill_template(template_bytes, {"dob": "5/22/1953"})
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest -q letters/tests/test_template_fill.py`
Expected: `ModuleNotFoundError: No module named 'letters.docgen.template_fill'`.

- [ ] **Step 3: Implement `template_fill.py`**

`letters/docgen/template_fill.py`:
```python
"""
Fill the Clinicals Request .docx template.

Every variable in the template is a Word content control (w:sdt) bound to a
document property via w:dataBinding/@w:xpath. We write each value into the
control's visible text AND into the property part it is bound to, so Word's
own binding refresh agrees with what we wrote.
"""
import copy
import datetime as dt
import io
import logging
import re
import zipfile

from lxml import etree

log = logging.getLogger(__name__)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC = "http://purl.org/dc/elements/1.1/"
EP = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
COVER = "http://schemas.microsoft.com/office/2006/coverPageProps"
NS = {"w": W}

# last element of the binding xpath -> our field name
FIELD_BINDINGS = {
    "keywords": "policy_id",
    "category": "member_name",
    "PublishDate": "dob",
    "contentStatus": "admission",
    "Abstract": "attn",
    "Company": "client",
    "creator": "doctor",
}

# field name -> element (Clark notation) in each property part
CORE_PROPS = {
    "policy_id": f"{{{CP}}}keywords",
    "member_name": f"{{{CP}}}category",
    "admission": f"{{{CP}}}contentStatus",
    "doctor": f"{{{DC}}}creator",
}
APP_PROPS = {"client": f"{{{EP}}}Company"}
COVER_PROPS = {"attn": f"{{{COVER}}}Abstract", "dob_iso": f"{{{COVER}}}PublishDate"}

_XPATH_LAST = re.compile(r"/(?:[\w.]+:)?([\w.]+)(?:\[\d+\])?$")


def binding_name(xpath: str | None) -> str | None:
    """'/ns1:coreProperties[1]/ns1:keywords[1]' -> 'keywords'."""
    if not xpath:
        return None
    m = _XPATH_LAST.search(xpath)
    return m.group(1) if m else None


def format_date(d: dt.date) -> str:
    """Word's M/d/yyyy: no leading zeros."""
    return f"{d.month}/{d.day}/{d.year}"


def fill_template(template_bytes: bytes, values: dict) -> bytes:
    values = dict(values)
    if "dob" in values and values["dob"] is not None:
        dob = values["dob"]
        if not isinstance(dob, dt.date):
            raise TypeError("dob must be a datetime.date")
        values["dob_iso"] = f"{dob.year:04d}-{dob.month:02d}-{dob.day:02d}T00:00:00Z"
        values["dob"] = format_date(dob)

    src = zipfile.ZipFile(io.BytesIO(template_bytes))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/document.xml":
                data = _fill_document(data, values)
            elif item.filename == "docProps/core.xml":
                data = _set_props(data, CORE_PROPS, values)
            elif item.filename == "docProps/app.xml":
                data = _set_props(data, APP_PROPS, values)
            elif item.filename.startswith("customXml/item") and b"CoverPageProperties" in data:
                data = _set_props(data, COVER_PROPS, values)
            out.writestr(item, data)
    return buf.getvalue()


def _serialize(root) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _set_props(xml_bytes: bytes, mapping: dict, values: dict) -> bytes:
    root = etree.fromstring(xml_bytes)
    for field, tag in mapping.items():
        value = values.get(field)
        if value is None:
            continue
        el = root.find(tag)
        if el is None:
            el = etree.SubElement(root, tag)
        el.text = str(value)
    return _serialize(root)


def _fill_document(xml_bytes: bytes, values: dict) -> bytes:
    root = etree.fromstring(xml_bytes)
    filled: set[str] = set()
    for sdt in root.iter(f"{{{W}}}sdt"):
        pr = sdt.find("w:sdtPr", NS)
        binding = pr.find("w:dataBinding", NS) if pr is not None else None
        if binding is None:
            continue
        field = FIELD_BINDINGS.get(binding_name(binding.get(f"{{{W}}}xpath")))
        if field is None or values.get(field) is None:
            continue
        _set_sdt_text(sdt, pr, str(values[field]))
        if field == "dob":
            date_el = pr.find("w:date", NS)
            if date_el is not None:
                date_el.set(f"{{{W}}}fullDate", values["dob_iso"])
        filled.add(field)
    for field in FIELD_BINDINGS.values():
        if values.get(field) is not None and field not in filled:
            log.warning("Template has no content control bound for field %r", field)
    return _serialize(root)


def _set_sdt_text(sdt, pr, text: str) -> None:
    for plc in pr.findall("w:showingPlcHdr", NS):
        pr.remove(plc)
    content = sdt.find("w:sdtContent", NS)
    if content is None:
        content = etree.SubElement(sdt, f"{{{W}}}sdtContent")
    rpr = _pick_run_properties(sdt, content)

    paragraphs = content.findall("w:p", NS)
    if paragraphs:  # block-level control: keep first paragraph (and its pPr), drop the rest
        container = paragraphs[0]
        for extra in paragraphs[1:]:
            content.remove(extra)
        for child in list(container):
            if child.tag != f"{{{W}}}pPr":
                container.remove(child)
    else:  # inline control
        container = content
        for child in list(container):
            container.remove(child)

    run = etree.SubElement(container, f"{{{W}}}r")
    if rpr is not None:
        run.append(rpr)
    t = etree.SubElement(run, f"{{{W}}}t")
    t.text = text
    t.set(f"{{{XML_NS}}}space", "preserve")


def _pick_run_properties(sdt, content):
    """
    Formatting for the new text, in order of preference:
    1. the control's existing run, if it is real text (not the grey placeholder style);
    2. the label run that precedes the control in the same paragraph;
    3. Arial 15pt #333333 (the template's header-block style).
    """
    for run in content.iter(f"{{{W}}}r"):
        rpr = run.find("w:rPr", NS)
        if rpr is not None and rpr.find("w:rStyle[@w:val='PlaceholderText']", NS) is None:
            return copy.deepcopy(rpr)
    prev = sdt.getprevious()
    while prev is not None:
        if prev.tag == f"{{{W}}}r":
            rpr = prev.find("w:rPr", NS)
            if rpr is not None:
                rpr = copy.deepcopy(rpr)
                for style in rpr.findall("w:rStyle", NS):
                    rpr.remove(style)
                return rpr
        prev = prev.getprevious()
    rpr = etree.Element(f"{{{W}}}rPr")
    fonts = etree.SubElement(rpr, f"{{{W}}}rFonts")
    for attr in ("ascii", "hAnsi", "cs"):
        fonts.set(f"{{{W}}}{attr}", "Arial")
    etree.SubElement(rpr, f"{{{W}}}color").set(f"{{{W}}}val", "333333")
    etree.SubElement(rpr, f"{{{W}}}sz").set(f"{{{W}}}val", "30")
    etree.SubElement(rpr, f"{{{W}}}szCs").set(f"{{{W}}}val", "30")
    return rpr
```

- [ ] **Step 4: Run the tests**

Run: `pytest -q letters/tests/test_template_fill.py`
Expected: `9 passed`. If `test_fills_every_bound_control_including_duplicates` fails on `PublishDate` because the template's date control text differs, print `_sdt_texts(template_bytes)` and adjust only the expected *original* texts in `test_missing_values_leave_controls_alone` — never the filled expectations.

- [ ] **Step 5: Eyeball the result in Word (manual, 1 minute)**

```powershell
python -c "import datetime as dt; from letters.docgen import TEMPLATE_FIXTURE; from letters.docgen.template_fill import fill_template; open('sample.docx','wb').write(fill_template(TEMPLATE_FIXTURE.read_bytes(), dict(policy_id='WT-123456', member_name='JOHN SMITH', dob=dt.date(1953,5,22), admission='9/15/2026', attn='UR DEPARTMENT', client='WORLDTRIPS', doctor='RICHARD ABDALLAH')))"
Start-Process sample.docx
```
Expected: Word opens with all seven values in place, no grey placeholders, logo and footer intact, values keep the label's font. Close Word and delete `sample.docx`.

- [ ] **Step 6: Commit**

```powershell
git add letters/docgen letters/tests/test_template_fill.py
git commit -m "Fill Word content controls and document properties from field values

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---
### Task 4: `pdf_convert.py` — `.docx` → `.pdf` via Word (with `fake` and `libreoffice` implementations)

**Files:**
- Create: `letters/docgen/pdf_convert.py`, `letters/tests/test_pdf_convert.py`

**Interfaces:**
- Consumes: `settings.PDF_CONVERTER`, `settings.WORD_TIMEOUT_SECONDS` (Task 1); `fill_template` (Task 3) in the Word integration test only.
- Produces: `convert(docx_path: Path, pdf_path: Path, converter: str | None = None) -> None` (default converter from settings), `ConversionError(RuntimeError)`, `word_available() -> bool`.

- [ ] **Step 1: Write the failing tests**

`letters/tests/test_pdf_convert.py`:
```python
import datetime as dt

import pytest

from letters.docgen.pdf_convert import ConversionError, convert, word_available


def _docx(tmp_path):
    src = tmp_path / "a.docx"
    src.write_bytes(b"not really a docx")
    return src


def test_fake_converter_writes_a_pdf_and_creates_parent_dir(tmp_path):
    out = tmp_path / "sub" / "a.pdf"
    convert(_docx(tmp_path), out, converter="fake")
    assert out.read_bytes().startswith(b"%PDF")


def test_missing_source_raises(tmp_path):
    with pytest.raises(ConversionError):
        convert(tmp_path / "nope.docx", tmp_path / "a.pdf", converter="fake")


def test_unknown_converter_raises(tmp_path):
    with pytest.raises(ConversionError):
        convert(_docx(tmp_path), tmp_path / "a.pdf", converter="bogus")


def test_default_converter_comes_from_settings(tmp_path, settings):
    settings.PDF_CONVERTER = "fake"
    out = tmp_path / "a.pdf"
    convert(_docx(tmp_path), out)
    assert out.exists()


@pytest.mark.word
@pytest.mark.skipif(not word_available(), reason="Microsoft Word not installed")
def test_word_converts_the_filled_template(tmp_path, template_bytes):
    from letters.docgen.template_fill import fill_template

    src = tmp_path / "letter.docx"
    src.write_bytes(fill_template(template_bytes, dict(
        policy_id="WT-1", member_name="JOHN SMITH", dob=dt.date(1953, 5, 22), admission="9/15/2026")))
    out = tmp_path / "letter.pdf"
    convert(src, out, converter="word")
    assert out.read_bytes()[:5] == b"%PDF-"
    assert out.stat().st_size > 10_000  # a real one-page letter with the logo
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest -q letters/tests/test_pdf_convert.py`
Expected: `ModuleNotFoundError: No module named 'letters.docgen.pdf_convert'`.

- [ ] **Step 3: Implement `pdf_convert.py`**

`letters/docgen/pdf_convert.py`:
```python
"""
Turn a .docx into a .pdf. `word` (default) automates Microsoft Word through
COM; `libreoffice` shells out to soffice; `fake` writes a minimal PDF for tests.
"""
import logging
import shutil
import subprocess
import threading
from pathlib import Path

from django.conf import settings

log = logging.getLogger(__name__)

WINWORD = Path(r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE")
WD_EXPORT_FORMAT_PDF = 17
WD_DO_NOT_SAVE_CHANGES = 0

MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


class ConversionError(RuntimeError):
    pass


def word_available() -> bool:
    return WINWORD.exists()


def convert(docx_path: Path, pdf_path: Path, converter: str | None = None) -> None:
    converter = (converter or settings.PDF_CONVERTER).lower()
    docx_path, pdf_path = Path(docx_path), Path(pdf_path)
    if not docx_path.exists():
        raise ConversionError(f"Source document not found: {docx_path}")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    if converter == "fake":
        pdf_path.write_bytes(MINIMAL_PDF)
    elif converter == "word":
        _convert_word(docx_path, pdf_path, settings.WORD_TIMEOUT_SECONDS)
    elif converter == "libreoffice":
        _convert_libreoffice(docx_path, pdf_path, settings.WORD_TIMEOUT_SECONDS)
    else:
        raise ConversionError(f"Unknown pdf_converter {converter!r} in mapinc.ini")

    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise ConversionError(f"{converter} produced no PDF at {pdf_path}")


# --- Word -------------------------------------------------------------------

_word_lock = threading.Lock()  # one Word conversion at a time, process-wide


def _convert_word(docx_path: Path, pdf_path: Path, timeout: int) -> None:
    """Run Word in a worker thread so a hung WINWORD can be abandoned and killed."""
    with _word_lock:
        before = _winword_pids()
        errors: list[BaseException] = []
        worker = threading.Thread(target=_word_export, args=(docx_path, pdf_path, errors), daemon=True)
        worker.start()
        worker.join(timeout)
        if worker.is_alive():
            for pid in _winword_pids() - before:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
            raise ConversionError(f"Word did not finish within {timeout}s; its process was killed")
        if errors:
            raise ConversionError(f"Word failed: {errors[0]}") from errors[0]


def _word_export(docx_path: Path, pdf_path: Path, errors: list) -> None:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    word = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(docx_path), ReadOnly=True, AddToRecentFiles=False)
        try:
            doc.ExportAsFixedFormat(str(pdf_path), WD_EXPORT_FORMAT_PDF)
        finally:
            doc.Close(WD_DO_NOT_SAVE_CHANGES)
    except BaseException as exc:  # noqa: BLE001 - surfaced to the caller thread
        errors.append(exc)
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:  # noqa: BLE001
                log.exception("Word.Quit failed")
        pythoncom.CoUninitialize()


def _winword_pids() -> set[int]:
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq WINWORD.EXE", "/FO", "CSV", "/NH"],
        capture_output=True, text=True).stdout
    pids = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.strip().split('","')]
        if len(parts) >= 2 and parts[0].upper() == "WINWORD.EXE" and parts[1].isdigit():
            pids.add(int(parts[1]))
    return pids


# --- LibreOffice ------------------------------------------------------------

def _convert_libreoffice(docx_path: Path, pdf_path: Path, timeout: int) -> None:
    soffice = shutil.which("soffice") or r"C:\Program Files\LibreOffice\program\soffice.exe"
    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(pdf_path.parent), str(docx_path)],
        capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise ConversionError(result.stderr.strip() or "LibreOffice conversion failed")
    produced = pdf_path.parent / f"{docx_path.stem}.pdf"
    if produced != pdf_path:
        produced.replace(pdf_path)
```

- [ ] **Step 4: Run the tests**

Run: `pytest -q letters/tests/test_pdf_convert.py`
Expected: `5 passed` on this machine (Word present; the Word test takes a few seconds). On a machine without Word: `4 passed, 1 skipped`.

- [ ] **Step 5: Commit**

```powershell
git add letters/docgen/pdf_convert.py letters/tests/test_pdf_convert.py
git commit -m "Add docx-to-PDF conversion via Word COM with fake and LibreOffice backends

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `filenames.py` — safe PDF filenames and folder resolution

**Files:**
- Create: `letters/docgen/filenames.py`, `letters/tests/test_filenames.py`

**Interfaces:**
- Produces:
  - `build_filename(pattern: str, *, member_name: str, policy_id: str, case_encounter: str, today: date) -> str` — always ends in `.pdf`.
  - `resolve_folder(root: str, folder_name: str) -> Path` — raises `InvalidFolderName(ValueError)` for empty root, empty name, `..`, absolute paths or drive letters.
  - `safe_component(value: str) -> str`.

- [ ] **Step 1: Write the failing tests**

`letters/tests/test_filenames.py`:
```python
import datetime as dt
from pathlib import Path

import pytest

from letters.docgen.filenames import InvalidFolderName, build_filename, resolve_folder, safe_component

TODAY = dt.date(2026, 9, 19)


def test_default_pattern():
    name = build_filename("CLINICALS REQUEST-{member_name}-SENT{MMDDYY}.pdf",
                          member_name="JOHN SMITH", policy_id="P1", case_encounter="E1", today=TODAY)
    assert name == "CLINICALS REQUEST-JOHN SMITH-SENT091926.pdf"


def test_all_placeholders_and_missing_extension():
    name = build_filename("{case_encounter}_{policy_id}_{YYYYMMDD}",
                          member_name="x", policy_id="P/1", case_encounter="E:1", today=TODAY)
    assert name == "E1_P1_20260919.pdf"


def test_safe_component_strips_illegal_characters():
    assert safe_component('SMITH, JOHN <jr>?*|"') == "SMITH, JOHN jr"
    assert safe_component("...") == "_"


def test_resolve_folder_joins_nested_names():
    assert resolve_folder(r"\\server\claims", "2026/SMITH_JOHN") == Path(r"\\server\claims\2026\SMITH_JOHN")
    assert resolve_folder(r"C:\claims", "SMITH_JOHN") == Path(r"C:\claims\SMITH_JOHN")


@pytest.mark.parametrize("bad", ["", "   ", "..", r"..\other", r"a\..\b", r"C:\x", r"\\other\share", "/abs", r"\abs"])
def test_resolve_folder_rejects_escapes(bad):
    with pytest.raises(InvalidFolderName):
        resolve_folder(r"C:\claims", bad)


def test_resolve_folder_requires_root():
    with pytest.raises(InvalidFolderName):
        resolve_folder("", "SMITH")
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest -q letters/tests/test_filenames.py`
Expected: `ModuleNotFoundError: No module named 'letters.docgen.filenames'`.

- [ ] **Step 3: Implement `filenames.py`**

`letters/docgen/filenames.py`:
```python
"""Filename pattern expansion and safe sub-folder resolution."""
import re
from datetime import date
from pathlib import Path

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class InvalidFolderName(ValueError):
    pass


def safe_component(value: str) -> str:
    """Strip characters Windows does not allow in file names."""
    cleaned = _ILLEGAL.sub("", str(value)).strip().rstrip(".").strip()
    return cleaned or "_"


def build_filename(pattern: str, *, member_name: str, policy_id: str, case_encounter: str, today: date) -> str:
    name = pattern.format(
        member_name=safe_component(member_name),
        policy_id=safe_component(policy_id),
        case_encounter=safe_component(case_encounter),
        MMDDYY=today.strftime("%m%d%y"),
        YYYYMMDD=today.strftime("%Y%m%d"),
    ).strip()
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


def resolve_folder(root: str, folder_name: str) -> Path:
    """Join `folder_name` (from the query string) under `root` (from admin settings), refusing escapes."""
    if not (root or "").strip():
        raise InvalidFolderName("PDF root folder is not set. Set it in admin > Settings.")
    name = (folder_name or "").strip().replace("/", "\\")
    if not name:
        raise InvalidFolderName("Folder name is required.")
    if name.startswith("\\"):
        raise InvalidFolderName("Folder name must be a sub-folder name, not an absolute path.")
    parts = [p.strip() for p in name.split("\\") if p.strip()]
    if any(p == ".." or ":" in p for p in parts):
        raise InvalidFolderName("Folder name may not contain '..' or a drive letter.")
    return Path(root.strip()).joinpath(*parts)
```

- [ ] **Step 4: Run the tests**

Run: `pytest -q letters/tests/test_filenames.py`
Expected: all pass (13 tests including parametrized cases).

- [ ] **Step 5: Commit**

```powershell
git add letters/docgen/filenames.py letters/tests/test_filenames.py
git commit -m "Add PDF filename pattern expansion and safe folder resolution

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---
### Task 6: `service.py` — `generate_letter()` orchestration and upsert

**Files:**
- Create: `letters/docgen/service.py`, `letters/tests/test_service.py`

**Interfaces:**
- Consumes: `fill_template` (Task 3), `convert`/`ConversionError` (Task 4), `build_filename`/`resolve_folder`/`InvalidFolderName` (Task 5), `AppSettings.load()`, `AppSettings.template_bytes()`, `Letter` (Task 2), fixtures `app_settings` (Task 2).
- Produces:
  - `generate_letter(data: dict, windows_user: str) -> Letter` — `data` keys: `case_encounter, policy_id, member_name, dob (date), admission, folder_name` (extra keys ignored).
  - `LetterGenerationError(Exception)` — message is safe to show to the user.

- [ ] **Step 1: Write the failing tests**

`letters/tests/test_service.py`:
```python
import datetime as dt
from pathlib import Path

import pytest

from letters.docgen.pdf_convert import ConversionError
from letters.docgen.service import LetterGenerationError, generate_letter
from letters.models import Letter
from letters.tests.test_template_fill import _sdt_texts

DATA = dict(case_encounter="E-100", policy_id="WT-123456", member_name="JOHN SMITH",
            dob=dt.date(1953, 5, 22), admission="9/15/2026", folder_name="SMITH_JOHN")


@pytest.fixture(autouse=True)
def fake_converter(settings):
    settings.PDF_CONVERTER = "fake"


@pytest.mark.django_db
def test_creates_letter_files_and_audit_fields(app_settings):
    letter = generate_letter(DATA, "DOMAIN\\rabdallah")
    pdf = Path(letter.pdf_path)
    assert pdf.parent == Path(app_settings.pdf_root_folder) / "SMITH_JOHN"
    assert pdf.name.startswith("CLINICALS REQUEST-JOHN SMITH-SENT") and pdf.suffix == ".pdf"
    assert pdf.read_bytes().startswith(b"%PDF")
    assert Path(letter.docx_path) == pdf.with_suffix(".docx") and Path(letter.docx_path).exists()
    assert (letter.attn, letter.client, letter.doctor) == ("UR DEPARTMENT", "WORLDTRIPS", "RICHARD ABDALLAH")
    assert letter.created_by == letter.modified_by == "DOMAIN\\rabdallah"
    assert letter.created_at is not None and letter.modified_at is not None
    assert Letter.objects.count() == 1


@pytest.mark.django_db
def test_docx_contains_the_values_and_snapshotted_defaults(app_settings):
    letter = generate_letter(DATA, "u")
    texts = _sdt_texts(Path(letter.docx_path).read_bytes())
    assert texts["keywords"] == ["WT-123456"]
    assert texts["PublishDate"] == ["5/22/1953"]
    assert texts["Company"] == ["WORLDTRIPS", "WORLDTRIPS"]


@pytest.mark.django_db
def test_update_keeps_created_by_and_replaces_old_files(app_settings):
    first = generate_letter(DATA, "alice")
    old_pdf, old_docx = Path(first.pdf_path), Path(first.docx_path)
    second = generate_letter({**DATA, "member_name": "JANE SMITH"}, "bob")
    assert second.pk == first.pk
    assert (second.created_by, second.modified_by) == ("alice", "bob")
    assert second.modified_at > first.modified_at
    assert second.member_name == "JANE SMITH"
    assert not old_pdf.exists() and not old_docx.exists()
    assert Path(second.pdf_path).exists() and "JANE SMITH" in second.pdf_path
    assert Letter.objects.count() == 1


@pytest.mark.django_db
def test_blank_user_becomes_unknown(app_settings):
    assert generate_letter(DATA, "  ").created_by == "unknown"


@pytest.mark.django_db
def test_invalid_folder_name_saves_nothing(app_settings):
    with pytest.raises(LetterGenerationError):
        generate_letter({**DATA, "folder_name": r"..\x"}, "u")
    assert Letter.objects.count() == 0


@pytest.mark.django_db
def test_missing_root_folder_is_reported(app_settings):
    app_settings.pdf_root_folder = ""
    app_settings.save()
    with pytest.raises(LetterGenerationError, match="root folder"):
        generate_letter(DATA, "u")


@pytest.mark.django_db
def test_converter_failure_saves_nothing(app_settings, monkeypatch):
    def boom(*args, **kwargs):
        raise ConversionError("Word exploded")

    monkeypatch.setattr("letters.docgen.service.convert", boom)
    with pytest.raises(LetterGenerationError, match="Word exploded"):
        generate_letter(DATA, "u")
    assert Letter.objects.count() == 0


@pytest.mark.django_db
def test_missing_required_field(app_settings):
    with pytest.raises(LetterGenerationError, match="member_name"):
        generate_letter({**DATA, "member_name": ""}, "u")
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest -q letters/tests/test_service.py`
Expected: `ModuleNotFoundError: No module named 'letters.docgen.service'`.

- [ ] **Step 3: Implement `service.py`**

`letters/docgen/service.py`:
```python
"""Generate one Clinicals Request letter end to end and record it."""
import logging
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from letters.models import AppSettings, Letter

from .filenames import InvalidFolderName, build_filename, resolve_folder
from .pdf_convert import ConversionError, convert
from .template_fill import fill_template

log = logging.getLogger(__name__)

REQUIRED_FIELDS = ("case_encounter", "policy_id", "member_name", "dob", "admission", "folder_name")


class LetterGenerationError(Exception):
    """Something the user can act on; the message is shown on the form."""


def generate_letter(data: dict, windows_user: str) -> Letter:
    for key in REQUIRED_FIELDS:
        if not data.get(key):
            raise LetterGenerationError(f"{key} is required.")
    windows_user = (windows_user or "").strip() or "unknown"

    s = AppSettings.load()
    values = dict(
        policy_id=data["policy_id"], member_name=data["member_name"], dob=data["dob"],
        admission=data["admission"],
        attn=s.attn_default, client=s.client_default, doctor=s.doctor_default,
    )
    try:
        folder = resolve_folder(s.pdf_root_folder, data["folder_name"])
        template = s.template_bytes()
    except (InvalidFolderName, ValueError) as exc:
        raise LetterGenerationError(str(exc)) from exc

    docx_bytes = fill_template(template, values)
    pdf_path = folder / build_filename(
        s.pdf_filename_pattern, member_name=data["member_name"], policy_id=data["policy_id"],
        case_encounter=data["case_encounter"], today=timezone.localdate())
    docx_path = pdf_path.with_suffix(".docx")

    try:
        folder.mkdir(parents=True, exist_ok=True)
        docx_path.write_bytes(docx_bytes)
        convert(docx_path, pdf_path)
    except (OSError, ConversionError) as exc:
        log.exception("Letter generation failed for case %s", data["case_encounter"])
        raise LetterGenerationError(f"Could not create the PDF: {exc}") from exc

    with transaction.atomic():
        letter = Letter.objects.filter(case_encounter=data["case_encounter"]).first()
        if letter is None:
            letter = Letter(case_encounter=data["case_encounter"], created_by=windows_user)
        else:
            _delete_old_files(letter, keep={str(pdf_path), str(docx_path)})
        letter.policy_id = data["policy_id"]
        letter.member_name = data["member_name"]
        letter.dob = data["dob"]
        letter.admission = data["admission"]
        letter.attn, letter.client, letter.doctor = values["attn"], values["client"], values["doctor"]
        letter.folder_name = data["folder_name"]
        letter.pdf_path = str(pdf_path)
        letter.docx_path = str(docx_path)
        letter.modified_by = windows_user
        letter.save()
    return letter


def _delete_old_files(letter: Letter, keep: set[str]) -> None:
    for old in (letter.pdf_path, letter.docx_path):
        if old and old not in keep:
            try:
                Path(old).unlink(missing_ok=True)
            except OSError:
                log.warning("Could not delete superseded file %s", old, exc_info=True)
```

- [ ] **Step 4: Run the tests**

Run: `pytest -q letters/tests/test_service.py`
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```powershell
git add letters/docgen/service.py letters/tests/test_service.py
git commit -m "Add generate_letter service: fill, convert, save files, upsert with audit

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---
### Task 7: Form, views, URLs and the Access-styled page

**Files:**
- Create: `letters/forms.py`, `letters/urls.py`, `letters/templates/letters/form.html`, `letters/templates/letters/success.html`, `letters/static/letters/access.css`, `letters/tests/test_views.py`
- Modify: `letters/views.py` (replace generated content), `mapinc/urls.py`

**Interfaces:**
- Consumes: `generate_letter`, `LetterGenerationError` (Task 6), `AppSettings`, `Letter` (Task 2).
- Produces: URL names `letter_form` (`/letter/`) and `letter_pdf` (`/letter/<case_encounter>/pdf/`); `LetterForm` with fields `case_encounter, policy_id, member_name, dob, admission, folder_name, user(hidden)`.

- [ ] **Step 1: Write the failing tests**

`letters/tests/test_views.py`:
```python
import datetime as dt

import pytest
from django.urls import reverse

from letters.models import Letter

VALID = {"case_encounter": "E1", "policy_id": "P1", "member_name": "JOHN SMITH", "dob": "1953-05-22",
         "admission": "9/15/2026", "folder_name": "SMITH", "user": "DOM\\bob"}


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
    assert initial["user"] == "DOM\\bob"
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
    assert letter.created_by == "DOM\\bob"
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest -q letters/tests/test_views.py`
Expected: `NoReverseMatch: Reverse for 'letter_form' not found`.

- [ ] **Step 3: Implement form, views and URLs**

`letters/forms.py`:
```python
from django import forms

DATE_INPUT_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"]


class LetterForm(forms.Form):
    case_encounter = forms.CharField(label="Case/Encounter", max_length=100)
    policy_id = forms.CharField(label="Policy ID No.", max_length=100)
    member_name = forms.CharField(label="Member Name", max_length=200)
    dob = forms.DateField(label="Date of Birth", input_formats=DATE_INPUT_FORMATS,
                          widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    admission = forms.CharField(label="Admission", max_length=200)
    folder_name = forms.CharField(label="Folder", max_length=300)
    user = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("autocomplete", "off")
```

`letters/views.py`:
```python
from pathlib import Path

from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from .docgen.service import LetterGenerationError, generate_letter
from .forms import LetterForm
from .models import AppSettings, Letter

QUERY_FIELDS = ("case_encounter", "policy_id", "member_name", "dob", "admission", "folder_name", "user")
LETTER_FIELDS = ("case_encounter", "policy_id", "member_name", "dob", "admission", "folder_name")


def _parse_dob(value: str):
    try:
        return LetterForm.base_fields["dob"].to_python(value)
    except ValidationError:
        return value  # let the form report it on submit


def _initial_from_request(request) -> dict:
    """Existing letter (by case_encounter) first, then query-string values override field by field."""
    initial: dict = {}
    case_encounter = request.GET.get("case_encounter", "").strip()
    if case_encounter:
        existing = Letter.objects.filter(case_encounter=case_encounter).first()
        if existing:
            initial.update({name: getattr(existing, name) for name in LETTER_FIELDS})
    for name in QUERY_FIELDS:
        value = (request.GET.get(name) or "").strip()
        if value:
            initial[name] = _parse_dob(value) if name == "dob" else value
    return initial


@require_http_methods(["GET", "POST"])
def letter_form(request):
    context = {"app_settings": AppSettings.load()}
    if request.method == "POST":
        form = LetterForm(request.POST)
        if form.is_valid():
            try:
                letter = generate_letter(form.cleaned_data, form.cleaned_data.get("user", ""))
            except LetterGenerationError as exc:
                form.add_error(None, str(exc))
            else:
                return render(request, "letters/success.html", {**context, "letter": letter})
    else:
        form = LetterForm(initial=_initial_from_request(request))
    return render(request, "letters/form.html", {**context, "form": form})


def letter_pdf(request, case_encounter: str):
    letter = get_object_or_404(Letter, case_encounter=case_encounter)
    path = Path(letter.pdf_path) if letter.pdf_path else None
    if path is None or not path.is_file():
        raise Http404("PDF not found")
    return FileResponse(open(path, "rb"), content_type="application/pdf", filename=path.name)
```

`letters/urls.py`:
```python
from django.urls import path

from . import views

urlpatterns = [
    path("letter/", views.letter_form, name="letter_form"),
    path("letter/<str:case_encounter>/pdf/", views.letter_pdf, name="letter_pdf"),
]
```

`mapinc/urls.py` (replace):
```python
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("letters.urls")),
    path("", RedirectView.as_view(pattern_name="letter_form", permanent=False)),
]
```

- [ ] **Step 4: Templates and stylesheet**

`letters/templates/letters/form.html`:
```html
{% load static %}<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Clinicals Request</title>
<link rel="stylesheet" href="{% static 'letters/access.css' %}">
</head>
<body>
<div class="access-form">
  <div class="titlebar">Clinicals Request</div>
  <form method="post" class="detail" novalidate>
    {% csrf_token %}
    {% if form.non_field_errors %}<div class="msgbar">{{ form.non_field_errors|join:" " }}</div>{% endif %}
    {% for field in form.visible_fields %}
      <div class="row{% if field.errors %} has-error{% endif %}">
        <label for="{{ field.id_for_label }}">{{ field.label }}:</label>
        {% if field.name == "folder_name" %}
          <div class="folder">
            <span class="root" title="Root folder from admin settings">{{ app_settings.pdf_root_folder|default:"(root folder not set)" }}\</span>{{ field }}
          </div>
        {% else %}
          {{ field }}
        {% endif %}
        {% if field.errors %}<div class="error">{{ field.errors|join:" " }}</div>{% endif %}
      </div>
    {% endfor %}
    {% for hidden in form.hidden_fields %}{{ hidden }}{% endfor %}
    <div class="footer-note">ATTN: {{ app_settings.attn_default }} &middot; Client: {{ app_settings.client_default }} &middot; Dr. {{ app_settings.doctor_default }}</div>
    <div class="buttons">
      <button type="submit" class="default">Save &amp; Create PDF</button>
      <button type="button" onclick="window.close()">Cancel</button>
    </div>
  </form>
  <div class="statusbar">Form View</div>
</div>
<script>
  // Enter in any text box submits (Access behaviour); the first empty box gets focus.
  document.querySelectorAll('.detail input[type=text]').forEach(function (el) {
    el.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); el.form.requestSubmit(); } });
  });
  var first = Array.prototype.find.call(document.querySelectorAll('.detail input:not([type=hidden])'), function (el) { return !el.value; });
  (first || document.querySelector('.detail input:not([type=hidden])')).focus();
</script>
</body>
</html>
```

`letters/templates/letters/success.html`:
```html
{% load static %}<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Clinicals Request</title>
<link rel="stylesheet" href="{% static 'letters/access.css' %}">
</head>
<body>
<div class="access-form">
  <div class="titlebar">Clinicals Request</div>
  <div class="detail success">
    <p><strong>PDF saved.</strong></p>
    <div class="path">{{ letter.pdf_path }}</div>
    <p>{{ letter.member_name }} &middot; Policy {{ letter.policy_id }} &middot; Case {{ letter.case_encounter }}</p>
    <p class="muted">Saved by {{ letter.modified_by }} on {{ letter.modified_at|date:"n/j/Y g:i A" }}. You can close this window.</p>
    <div class="buttons">
      <a class="button default" href="{% url 'letter_pdf' letter.case_encounter %}" target="_blank" rel="noopener">Open PDF</a>
      <a class="button" href="{% url 'letter_form' %}?case_encounter={{ letter.case_encounter|urlencode }}&amp;user={{ letter.modified_by|urlencode }}">Edit again</a>
      <button type="button" onclick="window.close()">Close</button>
    </div>
  </div>
  <div class="statusbar">Form View</div>
</div>
</body>
</html>
```

`letters/static/letters/access.css`:
```css
:root { font-family: "Segoe UI", Tahoma, sans-serif; font-size: 12px; }
html, body { margin: 0; background: #dcdcdc; color: #000; }
body { display: flex; justify-content: center; padding: 24px 16px; }
.access-form { width: 480px; max-width: 100%; background: #f0f0f0; border: 1px solid #6d6d6d; box-shadow: 2px 2px 6px rgba(0,0,0,.35); }
.titlebar { background: linear-gradient(#fdfdfd, #e5e5e5); border-bottom: 1px solid #a0a0a0; padding: 6px 10px; font-weight: 600; }
.detail { padding: 14px 16px 10px; }
.row { display: grid; grid-template-columns: 120px 1fr; align-items: center; gap: 4px 8px; margin-bottom: 8px; }
.row label { text-align: right; }
.row input[type=text], .row input[type=date] { width: 100%; box-sizing: border-box; border: 1px solid #7a7a7a; border-top-color: #404040; border-left-color: #404040; background: #fff; padding: 3px 4px; font: inherit; }
.row input:focus { outline: 2px solid #ffd54f; outline-offset: -1px; }
.folder { display: flex; align-items: center; gap: 4px; min-width: 0; }
.folder .root { color: #555; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 55%; }
.error { grid-column: 2; color: #c00; font-size: 11px; }
.has-error input { border-color: #c00; }
.msgbar { background: #fff4ce; border: 1px solid #d9b300; padding: 6px 8px; margin-bottom: 10px; }
.footer-note { color: #555; font-size: 11px; border-top: 1px dotted #aaa; padding-top: 6px; margin-top: 4px; }
.buttons { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
button, a.button { font: inherit; padding: 4px 14px; min-width: 90px; background: #e1e1e1; border: 1px solid #adadad; color: #000; text-decoration: none; text-align: center; cursor: pointer; }
button.default, a.button.default { border-color: #0078d7; box-shadow: inset 0 0 0 1px #0078d7; }
button:hover, a.button:hover { background: #e5f1fb; border-color: #0078d7; }
.statusbar { border-top: 1px solid #a0a0a0; background: #e8e8e8; padding: 3px 8px; font-size: 11px; color: #333; }
.success p { margin: 6px 0; }
.success .path { font-family: Consolas, monospace; font-size: 11px; word-break: break-all; background: #fff; border: 1px solid #7a7a7a; padding: 4px; }
.muted { color: #555; }
```

- [ ] **Step 5: Run the tests**

Run: `pytest -q letters/tests/test_views.py`
Expected: `8 passed`.

- [ ] **Step 6: Look at it in a browser (manual)**

```powershell
python manage.py migrate
python manage.py load_default_template
python manage.py runserver
```
Open `http://127.0.0.1:8000/letter/?case_encounter=E1&policy_id=WT-123456&member_name=JOHN%20SMITH&dob=5/22/1953&admission=9/15/2026&folder_name=SMITH_JOHN&user=DOM\me`.
Expected: grey Access-style card, fields pre-filled, DOB shows 05/22/1953 in the date box, footer line shows ATTN/Client/Dr. Submit will fail with "PDF root folder is not set" in the yellow message bar (admin isn't wired yet) — that is the expected state for this task. Stop the server.

- [ ] **Step 7: Commit**

```powershell
git add letters mapinc/urls.py
git commit -m "Add Access-styled letter form, success page and PDF download views

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---
### Task 8: Admin — singleton Settings with template validation, read-only Letters with Regenerate

**Files:**
- Modify: `letters/admin.py` (replace generated), `letters/docgen/template_fill.py` (add `missing_bindings`)
- Create: `letters/tests/test_admin.py`

**Interfaces:**
- Consumes: `AppSettings`, `Letter` (Task 2), `generate_letter`/`LetterGenerationError` (Task 6), `FIELD_BINDINGS`/`binding_name` (Task 3), URL name `letter_pdf` (Task 7).
- Produces: `missing_bindings(template_bytes: bytes) -> set[str]` (field names whose bound control is absent); admin URL names `admin:letters_appsettings_change`, `admin:letters_letter_changelist`; admin action `regenerate_pdf`.

- [ ] **Step 1: Write the failing tests**

`letters/tests/test_admin.py`:
```python
import datetime as dt
import io
import zipfile

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from lxml import etree

from letters.docgen.template_fill import missing_bindings
from letters.models import AppSettings, Letter

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

SETTINGS_POST = {
    "attn_default": "UR DEPT", "client_default": "WORLDTRIPS", "doctor_default": "RICHARD ABDALLAH",
    "pdf_root_folder": r"C:\claims", "pdf_filename_pattern": AppSettings.DEFAULT_FILENAME_PATTERN, "_save": "Save",
}


@pytest.fixture
def admin_client(client, db):
    User.objects.create_superuser("admin", "admin@example.com", "pw")
    client.login(username="admin", password="pw")
    return client


def _template_without(template_bytes: bytes, binding: str) -> bytes:
    """Copy of the template with every content-control binding to `binding` removed."""
    src = zipfile.ZipFile(io.BytesIO(template_bytes))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/document.xml":
                root = etree.fromstring(data)
                for el in list(root.iter(f"{{{W}}}dataBinding")):
                    if el.get(f"{{{W}}}xpath", "").endswith(f":{binding}[1]"):
                        el.getparent().remove(el)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            out.writestr(item, data)
    return buf.getvalue()


def test_missing_bindings(template_bytes):
    assert missing_bindings(template_bytes) == set()
    assert missing_bindings(_template_without(template_bytes, "keywords")) == {"policy_id"}


@pytest.mark.django_db
def test_settings_changelist_redirects_to_the_single_row(admin_client):
    r = admin_client.get(reverse("admin:letters_appsettings_changelist"))
    assert r.status_code == 302
    assert r.url == reverse("admin:letters_appsettings_change", args=[1])


@pytest.mark.django_db
def test_settings_page_renders_and_saves(admin_client, app_settings):
    url = reverse("admin:letters_appsettings_change", args=[1])
    assert admin_client.get(url).status_code == 200
    r = admin_client.post(url, SETTINGS_POST)
    assert r.status_code == 302
    s = AppSettings.load()
    assert s.attn_default == "UR DEPT" and s.pdf_root_folder == r"C:\claims"
    assert s.template  # existing upload kept when no new file is sent


@pytest.mark.django_db
def test_template_upload_accepts_the_real_template(admin_client, app_settings, template_bytes):
    url = reverse("admin:letters_appsettings_change", args=[1])
    r = admin_client.post(url, {**SETTINGS_POST, "template": SimpleUploadedFile("new.docx", template_bytes)})
    assert r.status_code == 302
    assert AppSettings.load().template_bytes() == template_bytes


@pytest.mark.django_db
def test_template_upload_rejects_docx_missing_a_binding(admin_client, app_settings, template_bytes):
    url = reverse("admin:letters_appsettings_change", args=[1])
    bad = _template_without(template_bytes, "keywords")
    r = admin_client.post(url, {**SETTINGS_POST, "template": SimpleUploadedFile("bad.docx", bad)})
    assert r.status_code == 200
    assert "policy_id" in r.content.decode()
    assert AppSettings.load().template_bytes() == template_bytes


@pytest.mark.django_db
def test_letters_list_and_regenerate_action(admin_client, app_settings, settings):
    settings.PDF_CONVERTER = "fake"
    letter = Letter.objects.create(
        case_encounter="E1", policy_id="P1", member_name="JOHN SMITH", dob=dt.date(1953, 5, 22),
        admission="9/15/2026", attn="a", client="c", doctor="d", folder_name="SMITH",
        pdf_path="", docx_path="", created_by="bob", modified_by="bob")
    r = admin_client.get(reverse("admin:letters_letter_changelist"))
    assert r.status_code == 200 and "JOHN SMITH" in r.content.decode()

    r = admin_client.post(reverse("admin:letters_letter_changelist"),
                          {"action": "regenerate_pdf", "_selected_action": [letter.pk]}, follow=True)
    letter.refresh_from_db()
    assert letter.pdf_path.endswith(".pdf")
    assert (letter.created_by, letter.modified_by) == ("bob", "admin")
    assert "PDF regenerated" in r.content.decode()


@pytest.mark.django_db
def test_letters_cannot_be_added_in_admin(admin_client):
    assert admin_client.get(reverse("admin:letters_letter_add")).status_code == 403
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest -q letters/tests/test_admin.py`
Expected: `ImportError: cannot import name 'missing_bindings'`.

- [ ] **Step 3: Add `missing_bindings` to `template_fill.py`**

Append to `letters/docgen/template_fill.py`:
```python
def missing_bindings(template_bytes: bytes) -> set[str]:
    """Field names (see FIELD_BINDINGS) that have no bound content control in the template."""
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(template_bytes)).read("word/document.xml"))
    found = {
        FIELD_BINDINGS[name]
        for binding in root.iter(f"{{{W}}}dataBinding")
        if (name := binding_name(binding.get(f"{{{W}}}xpath"))) in FIELD_BINDINGS
    }
    return set(FIELD_BINDINGS.values()) - found
```

- [ ] **Step 4: Implement `admin.py`**

`letters/admin.py`:
```python
from django import forms
from django.contrib import admin, messages
from django.db.models.fields.files import FieldFile
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html

from .docgen.service import LetterGenerationError, generate_letter
from .docgen.template_fill import missing_bindings
from .models import AppSettings, Letter

admin.site.site_header = "MAP Inc – Clinicals Request"
admin.site.site_title = "MAP Inc"
admin.site.index_title = "Administration"


class AppSettingsForm(forms.ModelForm):
    class Meta:
        model = AppSettings
        fields = "__all__"

    def clean_template(self):
        upload = self.cleaned_data.get("template")
        if upload and not isinstance(upload, FieldFile):  # a new file, not the stored one
            data = upload.read()
            upload.seek(0)
            try:
                missing = missing_bindings(data)
            except Exception as exc:  # noqa: BLE001 - not a readable .docx
                raise forms.ValidationError(f"Not a valid Word .docx file ({exc}).") from exc
            if missing:
                raise forms.ValidationError(
                    "Template is missing content controls bound to: " + ", ".join(sorted(missing)))
        return upload


@admin.register(AppSettings)
class AppSettingsAdmin(admin.ModelAdmin):
    form = AppSettingsForm
    fieldsets = (
        ("Letter defaults", {"fields": ("attn_default", "client_default", "doctor_default")}),
        ("PDF output", {"fields": ("pdf_root_folder", "pdf_filename_pattern")}),
        ("Word template", {"fields": ("template",)}),
    )

    def has_add_permission(self, request):
        return not AppSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:letters_appsettings_change", args=[AppSettings.load().pk]))


@admin.register(Letter)
class LetterAdmin(admin.ModelAdmin):
    list_display = ("case_encounter", "policy_id", "member_name", "created_by", "created_at",
                    "modified_by", "modified_at", "pdf_link")
    search_fields = ("case_encounter", "policy_id", "member_name")
    list_filter = ("created_at", "modified_at")
    readonly_fields = [f.name for f in Letter._meta.fields if f.name != "id"] + ["pdf_link"]
    actions = ["regenerate_pdf"]

    def has_add_permission(self, request):
        return False

    @admin.display(description="PDF")
    def pdf_link(self, obj):
        if not obj.pdf_path:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener">Open PDF</a>',
                           reverse("letter_pdf", args=[obj.case_encounter]))

    @admin.action(description="Regenerate PDF with stored values")
    def regenerate_pdf(self, request, queryset):
        for letter in queryset:
            data = {name: getattr(letter, name) for name in
                    ("case_encounter", "policy_id", "member_name", "dob", "admission", "folder_name")}
            try:
                generate_letter(data, request.user.get_username())
            except LetterGenerationError as exc:
                self.message_user(request, f"{letter.case_encounter}: {exc}", messages.ERROR)
            else:
                self.message_user(request, f"{letter.case_encounter}: PDF regenerated.", messages.SUCCESS)
```

- [ ] **Step 5: Run all tests**

Run: `pytest -q`
Expected: everything passes (≈55 tests; the Word test runs on this machine).

- [ ] **Step 6: Try the admin (manual)**

```powershell
python manage.py createsuperuser --username admin --email admin@example.com
python manage.py runserver
```
Open `http://127.0.0.1:8000/admin/`, log in, open **Settings**: set *PDF root folder* to `C:\Users\bhanu\Documents\Upwork\2026\Sept\Richard\pdf-test` and save. Then open the form URL from Task 7 Step 6 and submit: with `pdf_converter = word` in `mapinc.ini`, a real PDF appears under `pdf-test\SMITH_JOHN\`. Open it and check the letter. Stop the server.

- [ ] **Step 7: Commit**

```powershell
git add letters
git commit -m "Add admin: singleton settings with template validation, read-only letters with regenerate

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---
### Task 9: Production run script (Waitress + WhiteNoise), Access launcher module, README, end-to-end smoke test

**Files:**
- Create: `run.bat`, `access/LetterLauncher.bas`, `README.md` (replace the one-line stub), `letters/tests/test_static.py`
- Modify: `requirements.txt`, `mapinc/settings.py` (WhiteNoise)

**Interfaces:**
- Consumes: everything above.
- Produces: a runnable server (`run.bat`) that serves CSS without `DEBUG`, and the VBA entry point `OpenClinicalsLetter(caseEncounter, policyId, memberName, dob, admission, folderName)`.

- [ ] **Step 1: Write the failing static-file test**

`letters/tests/test_static.py`:
```python
def test_css_is_served_without_debug(client, settings):
    settings.DEBUG = False
    r = client.get("/static/letters/access.css")
    assert r.status_code == 200
    assert b".access-form" in b"".join(r.streaming_content)
```

Run: `pytest -q letters/tests/test_static.py`
Expected: FAIL — status 404 (nothing serves static files when DEBUG is off).

- [ ] **Step 2: Add WhiteNoise**

Append to `requirements.txt`:
```
whitenoise>=6.6
```
```powershell
pip install -r requirements.txt
```
In `mapinc/settings.py`, insert `"whitenoise.middleware.WhiteNoiseMiddleware",` directly after `"django.middleware.security.SecurityMiddleware",` in `MIDDLEWARE`, and add at the end of the file:
```python
# Serve /static/ from the app's static dirs without a collectstatic step (tiny LAN app).
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
```

Run: `pytest -q letters/tests/test_static.py`
Expected: PASS.

- [ ] **Step 3: `run.bat`**

`run.bat`:
```bat
@echo off
rem Starts the MAP Inc letter server on port 8000. Run from a console that stays open,
rem or install as a service with NSSM (see README).
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python manage.py migrate --noinput
if errorlevel 1 (
  echo Database migration failed - check mapinc.ini and that PostgreSQL is running.
  pause
  exit /b 1
)
waitress-serve --listen=0.0.0.0:8000 --threads=4 mapinc.wsgi:application
```

Verify: run `.\run.bat` in a second PowerShell window, open `http://127.0.0.1:8000/letter/` — the page renders with its grey Access styling (CSS loaded). Leave it running for Step 5, or Ctrl+C.

- [ ] **Step 4: Access launcher module**

`access/LetterLauncher.bas`:
```vb
Attribute VB_Name = "LetterLauncher"
Option Compare Database
Option Explicit

' ---------------------------------------------------------------------------
' Opens the MAP Inc "Clinicals Request" web form pre-filled for one case.
' Import this module into the Access database, set LETTER_BASE_URL, then call:
'   OpenClinicalsLetter Me.CaseEncounter, Me.PolicyID, Me.MemberName, Me.DOB, Me.Admission, Me.FolderName
' The folder name is the sub-folder under the PDF root configured in the web admin.
' ---------------------------------------------------------------------------

Private Const LETTER_BASE_URL As String = "http://SERVER-NAME:8000"   ' <-- change to the server running run.bat
Private Const EDGE_EXE As String = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

Public Sub OpenClinicalsLetter(ByVal caseEncounter As Variant, ByVal policyId As Variant, _
                               ByVal memberName As Variant, ByVal dob As Variant, _
                               ByVal admission As Variant, ByVal folderName As Variant)
    Dim url As String
    url = LETTER_BASE_URL & "/letter/?case_encounter=" & UrlEnc(Nz(caseEncounter, "")) & _
          "&policy_id=" & UrlEnc(Nz(policyId, "")) & _
          "&member_name=" & UrlEnc(Nz(memberName, "")) & _
          "&dob=" & UrlEnc(FormatDob(dob)) & _
          "&admission=" & UrlEnc(Nz(admission, "")) & _
          "&folder_name=" & UrlEnc(Nz(folderName, "")) & _
          "&user=" & UrlEnc(Environ("USERNAME"))
    OpenInAppWindow url
End Sub

Private Function FormatDob(ByVal dob As Variant) As String
    If IsDate(dob) Then
        FormatDob = Format(dob, "yyyy-mm-dd")
    Else
        FormatDob = Nz(dob, "")
    End If
End Function

Private Sub OpenInAppWindow(ByVal url As String)
    ' Edge "--app" mode opens a chromeless window that looks and behaves like a dialog.
    On Error GoTo Fallback
    If Dir(EDGE_EXE) = "" Then GoTo Fallback
    Shell """" & EDGE_EXE & """ --app=""" & url & """", vbNormalFocus
    Exit Sub
Fallback:
    On Error GoTo 0
    Application.FollowHyperlink url
End Sub

' Percent-encodes a string as UTF-8 for use in a query string.
Public Function UrlEnc(ByVal s As String) As String
    Dim bytes() As Byte, i As Long, out As String
    If Len(s) = 0 Then Exit Function
    bytes = Utf8Bytes(s)
    For i = LBound(bytes) To UBound(bytes)
        Select Case bytes(i)
            Case 48 To 57, 65 To 90, 97 To 122, 45, 46, 95, 126   ' 0-9 A-Z a-z - . _ ~
                out = out & Chr(bytes(i))
            Case Else
                out = out & "%" & Right("0" & Hex(bytes(i)), 2)
        End Select
    Next i
    UrlEnc = out
End Function

Private Function Utf8Bytes(ByVal s As String) As Byte()
    Dim stm As Object
    Set stm = CreateObject("ADODB.Stream")
    stm.Type = 2            ' text
    stm.Charset = "utf-8"
    stm.Open
    stm.WriteText s
    stm.Position = 0
    stm.Type = 1            ' binary
    stm.Position = 3        ' skip the UTF-8 BOM
    Utf8Bytes = stm.Read
    stm.Close
End Function
```

- [ ] **Step 5: End-to-end smoke test with Word (manual — this is the acceptance check)**

With `run.bat` running and `pdf_converter = word` in `mapinc.ini`:
1. In admin > Settings confirm *PDF root folder* is set (e.g. `C:\Users\bhanu\Documents\Upwork\2026\Sept\Richard\pdf-test`).
2. Open in Edge: `http://127.0.0.1:8000/letter/?case_encounter=E-2001&policy_id=WT-123456&member_name=JOHN%20SMITH&dob=5/22/1953&admission=9/15/2026&folder_name=SMITH_JOHN&user=DOM\rabdallah`
3. Click **Save & Create PDF**. Expected: success card with the path `…\pdf-test\SMITH_JOHN\CLINICALS REQUEST-JOHN SMITH-SENT<today>.pdf`; **Open PDF** shows the letter with all values, logo and footer.
4. Click **Edit again**, change Admission to `9/16/2026`, save. Expected: same record (admin > Letters shows one row, `modified_by = DOM\rabdallah`, modified time updated), PDF overwritten.
5. Open `http://127.0.0.1:8000/letter/?case_encounter=E-2001` with no other parameters. Expected: form pre-filled from the saved record.

Report the produced PDF path and a screenshot/description of the letter to the user.

- [ ] **Step 6: README**

`README.md`:
```markdown
# mapinc – Clinicals Request letter generator

Web form (opened from MS Access) that fills the Clinicals Request Word template,
exports a PDF with Microsoft Word into a per-case folder, and records every
letter in PostgreSQL with created/modified audit fields.

Design: `docs/superpowers/specs/2026-09-19-clinicals-letter-design.md`.

## Requirements (server)
- Windows with Microsoft Word installed
- Python 3.13 (`py -3.13`)
- PostgreSQL (local or on the network)

## First-time setup
```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item mapinc.ini.example mapinc.ini    # then edit: database host/name/user/password, secret_key
python manage.py migrate
python manage.py createsuperuser
python manage.py load_default_template
```
Start the server with `run.bat` (port 8000), open `http://<server>:8000/admin/`,
log in, and in **Settings** set the **PDF root folder** (e.g. `\\server\claims`).
Defaults for ATTN / Client / Doctor, the filename pattern and the Word template
are also edited there.

## Using it from Access
Import `access/LetterLauncher.bas`, set `LETTER_BASE_URL`, and call
`OpenClinicalsLetter caseEncounter, policyId, memberName, dob, admission, folderName`
from a button. Access passes the sub-folder name; the PDF is written to
`<PDF root folder>\<folder name>\CLINICALS REQUEST-<member>-SENT<mmddyy>.pdf`.
The Windows user name is recorded as created/modified by.

URL format (all values editable on the form):
`/letter/?case_encounter=…&policy_id=…&member_name=…&dob=yyyy-mm-dd&admission=…&folder_name=…&user=…`

## Configuration (`mapinc.ini`)
| key | meaning |
|---|---|
| `[database]` | PostgreSQL connection |
| `[app] pdf_converter` | `word` (default) or `libreoffice` |
| `[app] word_timeout_seconds` | kill a hung Word after this many seconds |
| `[app] allowed_hosts` | comma-separated host names, `*` for any |

## Running as a Windows service (optional)
Install [NSSM](https://nssm.cc/) and run `nssm install MapIncLetters "<repo>\run.bat"`.
The service account must be able to run Word and write to the PDF root folder.

## Tests
```powershell
pytest -q
```
Tests marked `word` need Microsoft Word and are skipped elsewhere.
```

- [ ] **Step 7: Full test run and commit**

Run: `pytest -q`
Expected: all pass.

```powershell
git add requirements.txt mapinc/settings.py run.bat access README.md letters/tests/test_static.py
git commit -m "Add run script with WhiteNoise, Access launcher module and README

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Self-review against the spec

| Spec section | Task |
|---|---|
| §2 environment, `mapinc.ini`, Word, Postgres | 1, 4, 9 |
| §3 template bindings (7 fields, `subject` untouched) | 3 |
| §4 `Letter` and `AppSettings` fields, singleton, admin users | 2, 8 (superuser in README) |
| §5 query-string prefill order and parameter names, `user` → `unknown` | 6 (unknown), 7 (prefill) |
| §6 `template_fill`, `pdf_convert` (word/libreoffice/fake, lock, timeout), `service` steps 1–7 | 3, 4, 6 |
| §7 form look, fields, folder prefix, footer line, success state, errors; VBA launcher | 7, 9 |
| §8 admin: settings validation, letters list/search/filter, Open PDF, Regenerate | 8 |
| §9 layout, `run.bat`, README service note | 1, 9 |
| §10 tests | every task; Word integration test in 4; manual smoke in 3, 7, 8, 9 |

Type/name consistency checked: `generate_letter(data, windows_user)`, `LetterGenerationError`, `convert(docx_path, pdf_path, converter=None)`, `ConversionError`, `fill_template(template_bytes, values)`, `missing_bindings`, `build_filename(pattern, *, member_name, policy_id, case_encounter, today)`, `resolve_folder(root, folder_name)`, `AppSettings.load()`, `AppSettings.template_bytes()`, URL names `letter_form` / `letter_pdf`, fixtures `template_bytes` / `app_settings` are used with the same signatures in every task.
