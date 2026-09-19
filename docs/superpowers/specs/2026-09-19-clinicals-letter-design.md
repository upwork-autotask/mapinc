# Clinicals Request Letter Generator — Design

**Date:** 2026-09-19
**Project:** mapinc (Medical Audit Professionals, Inc.)
**Status:** Approved design, ready for implementation planning

## 1. Purpose

Medical Audit Professionals sends a one-page "Clinicals Request" fax letter to
hospital UR departments. Today the letter is a Word template
(`FAX TEMPLATE-CLINICALS REQUESTS- PT NAME-SENTXXXXXX.docx`) filled in by hand.

This project is a small Django web application that:

1. Is opened from the company's MS Access application via a URL whose query
   string carries the case data.
2. Shows a compact, Access-styled form pre-filled from that query string
   (every value editable).
3. On submit, fills the Word template, converts it to PDF with Microsoft Word,
   saves the PDF into a per-case folder, and records the letter in PostgreSQL
   with an audit trail (created/modified by Windows user and timestamp).
4. Provides an admin panel (Django admin, login required) for defaults, the
   template file, the PDF root folder, and letter history.

## 2. Environment and constraints

| Item | Decision |
|---|---|
| Hosting | Windows PC/server on the office LAN, MS Word installed |
| Launch from Access | Default browser via `Shell "msedge.exe --app=<url>"` (or `FollowHyperlink`) |
| Database | PostgreSQL (local install for development/testing; office server in production) |
| DB connection settings | Hand-edited config file `mapinc.ini` — no UI |
| Admin password | Django's built-in `auth_user` table (hashed) |
| PDF conversion | Word via COM (default); LibreOffice headless as optional fallback |
| Python | 3.14 |
| Stack | Django (current LTS at build time), psycopg 3, lxml, pywin32, waitress, pytest-django |

The form page itself requires no login: it is reached on the LAN from Access,
and the acting Windows user is passed in the URL. `/admin/` requires login.

## 3. The Word template

Every variable in the template is a Word content control (`w:sdt`) bound to a
document property through `w:dataBinding/@w:xpath`. The generator identifies
controls by the last element of that xpath:

| xpath ends with | Property part | Field | Occurrences |
|---|---|---|---|
| `keywords` | `docProps/core.xml` `cp:keywords` | `policy_id` | 1 |
| `category` | `docProps/core.xml` `cp:category` | `member_name` | 2 (header block + body sentence) |
| `PublishDate` | `customXml/item1.xml` `PublishDate` | `dob`, rendered `M/d/yyyy` | 1 (date-picker control) |
| `contentStatus` | `docProps/core.xml` `cp:contentStatus` | `admission` | 2 |
| `Abstract` | `customXml/item1.xml` `Abstract` | `attn` | 1 |
| `Company` | `docProps/app.xml` `Company` | `client` | 2 |
| `creator` | `docProps/core.xml` `dc:creator` | `doctor` | 2 |
| `subject` | `docProps/core.xml` `dc:subject` | (title "CLINICALS REQUEST") | left untouched |

The header holds the company logo; the footer holds the fixed address, phone,
fax and web site. These are never modified.

`case_encounter` and `folder_name` are **not** printed on the letter.

## 4. Data model (app `letters`)

### `Letter` — one row per case/encounter

| Field | Type | Notes |
|---|---|---|
| `case_encounter` | CharField, unique | The key. Decides "load existing" vs "create new". |
| `policy_id` | CharField | |
| `member_name` | CharField | |
| `dob` | DateField | |
| `admission` | CharField | Free text as it appears on the letter (e.g. an admission date or status). |
| `attn`, `client`, `doctor` | CharField | Snapshot of the `AppSettings` defaults at generation time, so history shows what was actually printed. |
| `folder_name` | CharField | Subfolder name passed by Access; joined under `AppSettings.pdf_root_folder`. |
| `pdf_path` | CharField | Full path of the PDF last written. |
| `docx_path` | CharField | Full path of the filled `.docx` kept next to the PDF. |
| `created_by` | CharField | Windows user from the `user=` parameter; `"unknown"` if absent. |
| `created_at` | DateTimeField | Set server-side on insert. |
| `modified_by` | CharField | Windows user on the most recent save. |
| `modified_at` | DateTimeField | Set server-side on every save. |

### `AppSettings` — single row (singleton), edited in admin

| Field | Default | Notes |
|---|---|---|
| `attn_default` | `UR DEPARTMENT` | |
| `client_default` | `WORLDTRIPS` | |
| `doctor_default` | `RICHARD ABDALLAH` | Printed after "Dr." in two places. |
| `pdf_root_folder` | (empty; must be set) | Local or UNC path, e.g. `\\server\claims`. |
| `pdf_filename_pattern` | `CLINICALS REQUEST-{member_name}-SENT{MMDDYY}.pdf` | Placeholders: `{member_name}`, `{policy_id}`, `{case_encounter}`, `{MMDDYY}`, `{YYYYMMDD}`. Characters illegal in Windows filenames are stripped from substituted values. |
| `template` | (the supplied `.docx`, loaded by a management command) | FileField. Upload validates that all seven bound controls listed in §3 are present. |

### Admin users

Django's `auth_user`. One superuser is created at install time
(`manage.py createsuperuser`).

## 5. Request flow

```
Access ──URL──▶ GET /letter/?case_encounter=…&policy_id=…&member_name=…&dob=…
                              &admission=…&folder_name=…&user=…
                  → prefill: existing Letter row for case_encounter (if any),
                    then query-string values override field by field
                  → render Access-styled form

                POST /letter/
                  → validate
                  → generate_letter(): fill docx → Word → PDF → save files → upsert row
                  → render success state (PDF path, Open PDF link, "you can close this window")
                  → on any failure: re-render the form with the error, nothing saved
```

### Query-string parameters

| Parameter | Required | Format |
|---|---|---|
| `case_encounter` | yes | text |
| `policy_id` | no | text |
| `member_name` | no | text |
| `dob` | no | `yyyy-mm-dd` or `m/d/yyyy` |
| `admission` | no | text |
| `folder_name` | no | subfolder name (may contain `\` or `/` for nesting; `..`, drive letters and leading separators are rejected) |
| `user` | no | Windows user name; hidden field on the form; `"unknown"` if absent |

Missing optional parameters leave the field blank (or at the stored value if
the letter already exists). All fields except `user` are validated as required
on submit.

## 6. Document generation pipeline (`letters/docgen/`)

### `template_fill.py`

`fill_template(template_bytes: bytes, values: dict) -> bytes`

- Opens the `.docx` as a zip; parses `word/document.xml` with lxml.
- For each `w:sdt` whose `w:dataBinding/@w:xpath` ends with a known element
  name (§3): replaces the runs inside `w:sdtContent` with a single run holding
  the value, using the formatting of the sibling label run (Arial, 15 pt,
  colour `333333`) rather than the grey `PlaceholderText` style, and removes
  `w:showingPlcHdr`.
- Writes the same values into `docProps/core.xml`, `docProps/app.xml` and
  `customXml/item1.xml` so Word's data bindings agree with the text when the
  file is opened (otherwise Word refreshes the controls back to the stored
  property values). `PublishDate` is written as an ISO datetime.
- All other package parts are copied byte-for-byte.
- A value with no matching control logs a warning; a control with no value is
  left untouched. Neither is an error.

### `pdf_convert.py`

`convert(docx_path: Path, pdf_path: Path) -> None`, dispatching on
`[app] pdf_converter` in `mapinc.ini`:

- `word` (default): `win32com.client` → hidden `Word.Application`,
  `Documents.Open(docx)`, `ExportAsFixedFormat(pdf, wdExportFormatPDF)`,
  close without saving, quit. Guards: `pythoncom.CoInitialize()` per thread,
  a process-wide lock so only one conversion runs at a time, and a timeout
  (default 60 s) after which the Word process is killed and an error raised.
- `libreoffice`: `soffice --headless --convert-to pdf --outdir …`.
- `fake` (tests only): writes a minimal valid PDF.

### `service.py`

`generate_letter(data: dict, windows_user: str) -> Letter`

1. Load `AppSettings`; snapshot `attn`, `client`, `doctor`.
2. `fill_template()` → temp `.docx`.
3. Resolve `pdf_root_folder / folder_name`; reject invalid names (§5);
   create the folder if it does not exist.
4. Build the filename from `pdf_filename_pattern`; write `<name>.docx` and
   convert to `<name>.pdf` in the target folder.
5. If a `Letter` with this `case_encounter` already exists and its previous
   `pdf_path`/`docx_path` differ from the new ones, delete the old files.
6. Upsert `Letter` inside a transaction: set `created_by/at` on insert;
   always set `modified_by/at`.
7. Return the `Letter`.

Steps 2–4 run before any database write; a failure there leaves the database
unchanged and surfaces as a form error.

## 7. Form page (`/letter/`)

- Single fixed-width card (~480 px) centred on a `#F0F0F0` page, styled after
  an Access popup form: Segoe UI 9 pt, title strip "Clinicals Request",
  right-aligned labels, sunken white text boxes, bottom button row
  **Save & Create PDF** / **Cancel**.
- Plain HTML + one CSS file (`static/letters/access.css`); minimal JS (native
  date input, Enter submits).
- Fields, top to bottom: Case/Encounter, Policy ID, Member Name, Date of
  Birth, Admission, Folder (rendered as `<pdf_root_folder>\` prefix + editable
  `folder_name` box). Hidden: `user`.
- Read-only footer line showing what will print: `ATTN: … · Client: … · Dr. …`.
- Success state: same card; "PDF saved to `<path>`", **Open PDF** link
  (`/letter/<case_encounter>/pdf/` streams the file), and "You can close this
  window."
- Errors: field errors in red beneath the field; pipeline errors (folder,
  Word) in a message bar at the top. Form remains editable.

### Access side (`access/LetterLauncher.bas`)

Sample VBA: a `UrlEnc` helper and `OpenClinicalsLetter(encounter, policyId,
memberName, dob, admission, folderName)` that builds the URL, appends
`user=Environ("USERNAME")`, and runs `Shell "msedge.exe --app=" & url`
(falling back to `Application.FollowHyperlink`).

## 8. Admin (`/admin/`)

- **Settings** (`AppSettings`, singleton — add disabled after first row):
  all fields from §4; template upload validation as described.
- **Letters**: list shows case/encounter, policy ID, member name, created by/at,
  modified by/at, PDF path; search on case/encounter, policy ID, member name;
  filter by created date. Record view is read-only with an **Open PDF** link
  and a **Regenerate PDF** action that reruns `generate_letter()` with the
  stored values (audit `modified_by` = the admin username).
- **Users**: standard Django auth.

## 9. Configuration, layout, running

```
mapinc/
  manage.py  mapinc.ini.example  requirements.txt  run.bat  README.md
  mapinc/            settings.py (reads mapinc.ini)  urls.py  wsgi.py
  letters/
    models.py  forms.py  views.py  admin.py  urls.py
    docgen/    template_fill.py  pdf_convert.py  service.py
    templates/letters/   form.html  success.html
    static/letters/      access.css
    tests/
  access/            LetterLauncher.bas
  docs/superpowers/  specs/  plans/
```

`mapinc.ini` (next to `manage.py`, not committed; `mapinc.ini.example` is):

```ini
[database]
host = localhost
port = 5432
name = mapinc
user = mapinc
password = change-me

[app]
secret_key = change-me
allowed_hosts = *
debug = false
pdf_converter = word          ; word | libreoffice
word_timeout_seconds = 60
```

`run.bat` runs `waitress-serve --listen=0.0.0.0:8000 mapinc.wsgi:application`.
Installing as a Windows service (e.g. NSSM) is documented in the README but
not built.

## 10. Testing

- **`template_fill`**: fill the real template with sample values, reopen the
  result, assert each control's text (including the duplicated ones), the
  property parts, absence of `showingPlcHdr`, and that header/footer/media
  parts are byte-identical to the template. No Word needed.
- **`service`**: with the `fake` converter — create, update (audit fields,
  old-file cleanup), folder-name validation, filename pattern, rollback on
  converter failure.
- **`views`**: prefill from query string; prefill from existing row with
  query-string override; required-field errors; success page; PDF download.
- **`pdf_convert` (Word)**: one integration test, skipped unless Word is
  available; plus a manual smoke run producing a real PDF from the real
  template at the end of implementation.
- **Admin**: template upload validation accepts the real template and rejects
  a `.docx` missing a bound control.

## 11. Out of scope (for now)

- Login on the form page / URL signing.
- Windows service installation.
- Multiple templates or letter types.
- Reading the Access database directly.
- Faxing or emailing the PDF.
