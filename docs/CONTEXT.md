# Project context — decisions, state, and open items

Kept so work can continue from any machine with the full picture. Update it when
a decision changes or a milestone lands. Last updated: 2026-09-19.

## The client and the job
- Client: Medical Audit Professionals, Inc. (MAP), Pompano Beach FL — medical case
  management; contact is Dr. Richard Abdallah. Engagement via Upwork.
- MAP sends a one-page "Clinicals Request" fax letter to hospital UR departments
  asking for daily clinical records for an insured member (client: WORLDTRIPS / TMHCC).
- They run an MS Access "Case Tracker" application; letters were produced by hand
  in Word. Staff also work from Outlook.
- Their server: on-premises Windows Server **2012 R2** (out of support — flagged in
  the hardening plan), Microsoft Word installed, LAN clients. A Python 3.9 was on
  it; the app needs 3.10+ (3.13 target) — the venv had to be recreated.
- Some client resources (`javelina.hccmis.com`) are only reachable over their VPN;
  unrelated to this app.

## Decisions (with the why)
| Decision | Why |
|---|---|
| Fill the Word template by rewriting its content controls in Python (lxml), use Word only for PDF export | Template is used unmodified; generation is testable without Word; Word isolated behind a converter interface |
| Values are written to both the control text and the bound document properties | Otherwise Word "refreshes" the controls back to the stored property values |
| Letter key is `case_encounter` (one letter per encounter); `policy_id` is a plain field | Client's choice; a policy can have several encounters |
| ATTN / Client / Doctor are admin defaults, not on the form; snapshotted onto each `Letter` | Client wanted them fixed; snapshot keeps history accurate if defaults change |
| Access passes the **whole destination folder path**; the PDF-root setting was removed (2026-09-26) | Access already stores the full path per case. The form shows it read-only with an *Open folder* button; `MAPINC_ALLOWED_FOLDER_ROOTS` optionally limits where letters may be written, and relative paths / `..` are rejected |
| Filled `.docx` is kept next to the PDF | So a letter can be hand-edited in Word if needed |
| PDF conversion: Word COM with a process-wide lock, per-thread COM init, timeout + kill | Word automation is single-threaded and can hang |
| Launchers POST values to `/letter/handoff/` and open `/letter/?t=<token>` | Keeps patient data out of URLs, window titles and browser history |
| Handoff tokens: 5-minute TTL, single-use after save, optional LAN CIDR restriction | Minimise exposure of the stash |
| Launcher opens Edge `--app --new-window` in a private profile, dialog-sized, and (optionally) waits for the window to close | "Feels like an Access modal form"; private profile gives its own process so VBA can wait on it |
| Config via `MAPINC_*` env vars / `.env` (was `mapinc.ini`) | Client request; `ini_to_env` command converts old installs |
| Admin password = Django `auth_user` (hashed) | The "table maintaining the admin password" the client asked for |
| Custom Settings / Letters / Audit pages in the Access-style UI; Django admin kept for Users and the Regenerate action | Client wanted branded pages but not a full admin rewrite |
| HIPAA: app-level audit trail; RLS, pgcrypto and pgAudit deliberately **not** used | RLS needs per-user DB roles (we have one app role); pgcrypto breaks search; pgAudit has no Windows build. Rationale recorded in `docs/hipaa-hardening-plan.md` |
| Lockout is per **username** (not IP) | Whole office sits behind one NAT address |
| Windows identity via IIS Windows Authentication → `X-Remote-User` (`MAPINC_AUTH_MODE=remote_user`) | Makes `created_by/modified_by` a verified account instead of the launcher's self-reported name |

## Current state (all pushed to origin/main)
- Feature complete for v1: form, generation, admin, login, settings, letters list,
  audit log, launchers, HIPAA phase-3 code, deploy scripts. ~140 tests green.
- Dev machine (this repo's origin): PostgreSQL 18 local, role `mapinc`/`mapinc`,
  Django superusers `admin`/`admin123` (throwaway) and `report`/`M@pincrpt@2026*`.
  Test PDFs land in `..\pdf-test\`.
- Client machine: repo cloned under `D:\MAP_CONFERENCE ROOM\Case Tracker\DB\v10\mapinc`;
  they got as far as logging in. They still need `git pull`, venv on 3.13,
  `ini_to_env`, `pip install -r requirements.txt`, `migrate`.
- Server hardening phases 1, 2, 4, 5 (roles, TLS, firewall, IIS, backups, service)
  are scripted in `deploy/` but **not yet run** on the client server.

## Recent changes
- 2026-09-26: folder handling reworked (full path from the launcher, read-only
  field, *Open folder* button that copies the path to the clipboard), spinner
  while Word builds the PDF, `AppSettings.pdf_root_folder` removed
  (migration `0005_folder_full_path`).
- 2026-09-26: an existing letter opens in **view mode** — PDF details (name,
  created/changed by and when) with *View PDF* / *Edit* / *Open folder*. *Edit*
  (`?edit=1`) unlocks **Admission only** for ordinary users and **every field**
  for a signed-in admin (`is_staff`). Locking is enforced server-side: posted
  values for locked fields are replaced with the stored ones
  (`_editable_fields()` in `letters/views.py`).

## Open items / next steps
1. Client server: run the `deploy/` scripts in order (see `deploy/README.md`), then
   the §6 verification checklist in the hardening plan.
2. Decide `MAPINC_AUTH_MODE` for production: `remote_user` needs IIS + domain-joined
   PCs; fall back to `login` otherwise.
3. Delete the throwaway `admin` superuser on any real install.
4. Server 2012 R2 end-of-life: recommend migrating to 2019/2022.
5. Possible follow-ups the client hinted at: one-click launch from an Outlook email
   (parse fields from the message); faxing/emailing the PDF (out of scope so far).

## Where things are
- Repo: https://github.com/upwork-autotask/mapinc (public)
- Spec: `docs/superpowers/specs/2026-09-19-clinicals-letter-design.md`
- Implementation plan (historical, executed): `docs/superpowers/plans/2026-09-19-clinicals-letter.md`
- Hardening plan: `docs/hipaa-hardening-plan.md`; scripts: `deploy/`
- Brand assets: `assets/` (logo, letterhead); the form uses `letters/static/letters/map_logo.jpg`
- Original Word template: `letters/fixtures/clinicals_request_template.docx`
