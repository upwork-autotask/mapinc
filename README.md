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
## Starting the server
Double-click **`run.bat`** (or run it from a console). It activates the virtualenv,
applies any pending database migrations, and serves the app on port 8000 for every
network interface. Leave the window open — closing it stops the server.

```powershell
cd C:\path\to\mapinc
.\run.bat
```
Expected output ends with `INFO:waitress:Serving on http://0.0.0.0:8000`.

Then open:

| Page | URL |
|---|---|
| Letter form (what Access opens) | `http://<server>:8000/letter/` |
| Login | `http://<server>:8000/login/` |
| Settings — defaults, **PDF root folder**, filename pattern, Word template | `http://<server>:8000/settings/` |
| Letters — history, search, Open PDF, Edit | `http://<server>:8000/letters/` |
| Django admin — users, Regenerate PDF action | `http://<server>:8000/admin/` |

`<server>` is `localhost` on the machine itself, or the server's name / IP from
other PCs on the LAN (allow TCP 8000 through Windows Firewall for that).

Before the first letter: log in and set the **PDF root folder** in Settings
(e.g. `\\server\claims`).

**Stopping:** press `Ctrl+C` in the `run.bat` window, or close it.

**Developer mode** (auto-reloads code and templates on save, port 8000):
```powershell
.\.venv\Scripts\Activate.ps1
python manage.py runserver
```

**Troubleshooting**
- *"Database migration failed"* — PostgreSQL is not running or `mapinc.ini` has the wrong host/user/password.
- *"Missing mapinc.ini"* — copy `mapinc.ini.example` to `mapinc.ini` (see First-time setup).
- *Port already in use* — another copy is running; find it with `netstat -ano | findstr :8000` and stop it, or change the port in `run.bat`.
- *PDF not created / "Word did not finish"* — the account running `run.bat` must be able to start Microsoft Word; check `pdf_converter` and `word_timeout_seconds` in `mapinc.ini`.

## Using it from Access
Import `access/LetterLauncher.bas`, set `LETTER_BASE_URL`, and call
`OpenClinicalsLetter caseEncounter, policyId, memberName, dob, admission, folderName`
from a button. Access passes the sub-folder name; the PDF is written to
`<PDF root folder>\<folder name>\CLINICALS REQUEST-<member>-SENT<mmddyy>.pdf`
(the filled `.docx` is kept next to it). The Windows user name is recorded as
created/modified by. Opening the form again for the same case/encounter loads the
saved letter for editing; saving overwrites the PDF and updates the audit fields.

URL format (all values editable on the form):
`/letter/?case_encounter=…&policy_id=…&member_name=…&dob=yyyy-mm-dd&admission=…&folder_name=…&user=…`

## Configuration (`mapinc.ini`)
| key | meaning |
|---|---|
| `[database]` | PostgreSQL connection |
| `[app] pdf_converter` | `word` (default) or `libreoffice` |
| `[app] word_timeout_seconds` | kill a hung Word after this many seconds |
| `[app] allowed_hosts` | comma-separated host names, `*` for any |
| `[app] debug` | `true` only on a development machine |

## Running as a Windows service (optional)
Install [NSSM](https://nssm.cc/) and run `nssm install MapIncLetters "<repo>\run.bat"`.
The service account must be able to run Word and write to the PDF root folder.

## Tests
```powershell
pytest -q
```
Tests marked `word` need Microsoft Word and are skipped elsewhere.
