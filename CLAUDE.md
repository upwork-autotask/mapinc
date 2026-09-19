# mapinc — Clinicals Request letter generator

Django app for Medical Audit Professionals, Inc. (MAP). Opened from MS Access /
Outlook via a launcher, it fills the "Clinicals Request" Word template, exports a
PDF with Microsoft Word, stores the PDF in a per-case folder, and records every
letter in PostgreSQL with created/modified audit fields.

**Read first:** `docs/CONTEXT.md` (decisions + current state), then
`docs/superpowers/specs/2026-09-19-clinicals-letter-design.md` (design) and
`docs/hipaa-hardening-plan.md` (security plan, mostly implemented).

## Stack and layout
- Python 3.13 (3.10+ required), Django 5.2 LTS, PostgreSQL 18, psycopg 3, lxml,
  pywin32 (Word COM), waitress, whitenoise, django-axes, pytest-django.
- `letters/docgen/`: `template_fill.py` (content controls → values), `pdf_convert.py`
  (Word/LibreOffice/fake), `filenames.py`, `service.py` (`generate_letter()` orchestration).
- `letters/views.py`: letter form, PDF download, handoff endpoint, login/settings/list/audit pages.
- `letters/models.py`: `Letter` (key = `case_encounter`), `AppSettings` (singleton),
  `Handoff` (short-lived token stash), `AuditEvent` (insert-only trail).
- Access/Outlook launchers: `access/LetterLauncher.bas`, `outlook/LetterLauncher_Outlook.bas`.
- Server hardening scripts: `deploy/`.

## Configuration
All settings are `MAPINC_*` environment variables, read from `.env` next to
`manage.py` (`.env.example` is the template; `.env` is git-ignored). Real env
vars override the file. `MAPINC_ENV_FILE` selects another file. Old installs:
`python manage.py ini_to_env` converts `mapinc.ini`.

## Working conventions
- TDD: write the failing test in `letters/tests/`, run it, implement, run again, commit.
- Run tests with `.venv\Scripts\python.exe -m pytest -q` (≈140 tests, ~90 s; the
  Word test is skipped where Word is absent).
- Start the server with `run.bat` (Waitress on :8000). It runs `manage.py check`
  first and refuses to start if `MAPINC_PRODUCTION=true` and the config is unsafe.
  **Template/CSS edits need a server restart** (only `manage.py runserver` hot-reloads).
- Commit messages: imperative summary line; end with
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
- Push to `origin main` (https://github.com/upwork-autotask/mapinc, public).
- Bash heredocs containing HTML/VBA/backslashes have bitten us repeatedly on Windows —
  use the Write tool (or a Python patch script) for those files.

## Things not to change without asking
- The Word template's content-control bindings (`FIELD_BINDINGS` in `template_fill.py`).
- The letter key (`case_encounter`) and the audit fields on `Letter`.
- The hardening defaults in `mapinc/settings.py` and `letters/checks.py`.
