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
Copy-Item .env.example .env                # then edit: MAPINC_DB_* and MAPINC_SECRET_KEY
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
| Settings — letter defaults, filename pattern, Word template | `http://<server>:8000/settings/` |
| Letters — history, search, Open PDF, Edit | `http://<server>:8000/letters/` |
| Django admin — users, Regenerate PDF action | `http://<server>:8000/admin/` |

`<server>` is `localhost` on the machine itself, or the server's name / IP from
other PCs on the LAN (allow TCP 8000 through Windows Firewall for that).

Opening a case that already has a letter shows the PDF that is on record —
file name, who created it and when — with **View PDF**, **Edit** and **Open
folder** buttons. Edit lets an ordinary user change only **Admission**; an
administrator signed in to the app can change every field. Saving replaces the
PDF and records the change in the audit log.

The destination folder comes from the launcher with every letter, so there is
nothing to set up before the first letter. To restrict where letters may be
written, list the permitted folders in `MAPINC_ALLOWED_FOLDER_ROOTS`.

**Stopping:** press `Ctrl+C` in the `run.bat` window, or close it.

**Developer mode** (auto-reloads code and templates on save, port 8000):
```powershell
.\.venv\Scripts\Activate.ps1
python manage.py runserver
```

**Troubleshooting**
- *"mapinc requires Python 3.10 or newer"* or `TypeError: unsupported operand type(s) for |` — the virtualenv was created with an old Python (e.g. 3.9). Install Python 3.13, then `Remove-Item -Recurse .venv`, `py -3.13 -m venv .venv`, activate it and `pip install -r requirements.txt` again.
- *"Database migration failed"* — PostgreSQL is not running or the `MAPINC_DB_*` values in `.env` are wrong.
- *Still have a `mapinc.ini` from an older version?* — run `python manage.py ini_to_env` once; it writes the equivalent `.env`, then delete the ini.
- *Port already in use* — another copy is running; find it with `netstat -ano | findstr :8000` and stop it, or change the port in `run.bat`.
- *"Configuration check failed"* on start — `MAPINC_PRODUCTION=true` and something in `.env` is unsafe; the messages name the key (secret key, allowed_hosts, sslmode, database user, auth_mode, https, allow_query_prefill).
- *PDF not created / "Word did not finish"* — the account running `run.bat` must be able to start Microsoft Word; check `pdf_converter` and `word_timeout_seconds` in `mapinc.ini`.

## Using it from Access
Import `access/LetterLauncher.bas`, set `LETTER_BASE_URL`, and call
`OpenClinicalsLetterDialog caseEncounter, policyId, memberName, dob, admission, folderName`
from a button (opens a dialog-sized Edge window and waits until it is closed;
`OpenClinicalsLetter` is the non-blocking variant, and the module documents a
true Access modal form using the Edge Browser Control for Microsoft 365 Access).

**From Outlook (or Excel/Word) VBA:** import `outlook/LetterLauncher_Outlook.bas`
instead — same `OpenClinicalsLetterDialog` / `OpenClinicalsLetter` calls with no
Access dependencies, plus an `OpenLetterFromPrompt` macro for a ribbon button. Access passes the whole destination folder (e.g. `\\server\claims\SMITH_JOHN`); the PDF is written to
`<folder>\CLINICALS REQUEST-<member>-SENT<mmddyy>.pdf`
(the filled `.docx` is kept next to it). The Windows user name is recorded as
created/modified by. Opening the form again for the same case/encounter loads the
saved letter for editing; saving overwrites the PDF and updates the audit fields.

The launchers do not put patient data in the URL: they `POST` the values to
`/letter/handoff/` and open the short-lived link it returns (`/letter/?t=<token>`,
valid 15 minutes) in a new chromeless Edge window. The plain query-string form
still works for testing:
`/letter/?case_encounter=…&policy_id=…&member_name=…&dob=yyyy-mm-dd&admission=…&case_location=…&case_type=…&folder_name=…&user=…`

### PDF file name
Settings → **PDF filename pattern** builds the file name. Placeholders:
`{case_encounter}` `{policy_id}` `{member_name}` `{case_location}` `{case_type}`
`{user}` (who saved it, without the domain) `{MMDDYY}` `{YYYYMMDD}`. The default is

    {case_encounter}-{case_location}-{case_type}-CLINICALS REQUEST-{member_name}-SENT{MMDDYY}-{user}.pdf

Values the launcher did not send are left out and the extra separators removed.
A placeholder the app cannot fill is refused when the pattern is saved, and a
pattern already on record that cannot be filled is reported on the form instead
of failing the request.

`case_location` and `case_type` come from the launcher and are stored with the
letter; they appear in the file name only — they are not printed on the letter.

## Configuration (environment variables)
All settings are `MAPINC_*` environment variables. For convenience they are read
from a `.env` file next to `manage.py` (copy `.env.example`); a real environment
variable always overrides the file. `MAPINC_ENV_FILE` points at a different file
(used for migrations with the owner role in production).

| Variable | Meaning |
|---|---|
| `MAPINC_DB_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASSWORD` | PostgreSQL connection |
| `MAPINC_DB_SSLMODE`, `MAPINC_DB_SSLROOTCERT` | TLS to PostgreSQL (`require` or `verify-full` in production) |
| `MAPINC_SECRET_KEY` | Django secret key (long random string) |
| `MAPINC_ALLOWED_HOSTS` | comma-separated host names, `*` for any |
| `MAPINC_DEBUG` | `true` only on a development machine |
| `MAPINC_PDF_CONVERTER` | `word` (default) or `libreoffice` |
| `MAPINC_WORD_TIMEOUT_SECONDS` | kill a hung Word after this many seconds |
| `MAPINC_PRODUCTION` | `true` on the live server: the app refuses to start unless the settings below are safe |
| `MAPINC_AUTH_MODE` | `open` (LAN, no login), `login` (app login required), `remote_user` (IIS Windows Authentication) |
| `MAPINC_HTTPS`, `MAPINC_BEHIND_PROXY` | set when IIS terminates TLS in front of the app |
| `MAPINC_SESSION_MINUTES` | automatic logoff after this many idle minutes (default 30) |
| `MAPINC_LOCKOUT_FAILURES`, `MAPINC_LOCKOUT_MINUTES` | account lockout after failed sign-ins (5 / 15) |
| `MAPINC_ALLOW_QUERY_PREFILL` | allow PHI in the URL query string (dev only; launchers use handoff tokens) |
| `MAPINC_HANDOFF_ALLOWED_NETWORKS`, `MAPINC_HANDOFF_MINUTES` | who may create handoff links and how long they live |
| `MAPINC_ALLOWED_FOLDER_ROOTS` | folders letters may be written under (empty = wherever the launcher says) |
| `MAPINC_LISTEN` | address Waitress binds (`run.bat`; `127.0.0.1:8000` behind IIS) |

## HIPAA hardening
The application records an insert-only **audit trail** (letter opened / created /
updated / PDF downloaded / settings changed / login events) viewable at
`/audit/` with CSV export, enforces session timeout, password policy and login
lockout, keeps patient data out of URLs, and can tie every action to a verified
Windows account when run behind IIS. The plan is in
`docs/hipaa-hardening-plan.md`; the server-side scripts (database roles, TLS,
firewall, IIS, backups, service) are in `deploy/`.

## Running as a Windows service (optional)
Install [NSSM](https://nssm.cc/) and run `nssm install MapIncLetters "<repo>\run.bat"`.
The service account must be able to run Word and write to the PDF root folder.

## Tests
```powershell
pytest -q
```
Tests marked `word` need Microsoft Word and are skipped elsewhere.
