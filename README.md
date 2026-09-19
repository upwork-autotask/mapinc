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
are also edited there. **Letters** lists every generated letter with who created
and last modified it, an *Open PDF* link and a *Regenerate PDF* action.

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
