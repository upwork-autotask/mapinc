# HIPAA Technical Safeguards — On-Premises Hardening Plan for mapinc

**Scope:** the on-premises Windows server that runs PostgreSQL, the mapinc web app
(`run.bat` / Waitress), and Microsoft Word; the PDF root folder; the Access/Outlook
launchers on staff PCs. **Not in scope:** the organisation's administrative and
physical safeguards (risk analysis, policies, training, incident response) — those
are required too, but are not software work.

Guiding principle: the app is the **only** path to ePHI in the database. Most of
the "who viewed what" story is therefore best implemented in the app, with the
database locked down so that nothing else can get at the data directly.

## 0. Where the ePHI is (inventory)

| Location | Data | Today | Target |
|---|---|---|---|
| PostgreSQL `letters_letter` | member name, DOB, policy ID, admission, case no. | plain, role has `CREATEDB` | least-privilege roles, SSL-only, BitLocker |
| PostgreSQL `letters_handoff` | same values, 15-minute stash | plain | single-use, 5-minute TTL, purged |
| PDF root folder | the letters (.pdf + .docx) | NTFS defaults | NTFS ACL to the clinical group only, BitLocker |
| `media/templates/` | letter template (no PHI) | — | — |
| Server RAM / temp | Word conversion | — | temp files deleted after conversion (already) |
| Browser on staff PCs | letter form pages | token links only (no PHI in URLs) | HTTPS, no caching headers |
| Logs | Waitress/Django/Postgres logs | minimal | no PHI in logs, forwarded, retained 6 years |
| Backups | `pg_dump` | none defined | encrypted, tested, retained |

## Phase 1 — Database hardening (server config, ~half a day)

### 1.1 Roles: least privilege
Create three roles; the application never runs as `postgres`.

```sql
-- run as postgres
CREATE ROLE mapinc_owner   LOGIN PASSWORD '<strong>';            -- owns schema; used ONLY for manage.py migrate
CREATE ROLE mapinc_app     LOGIN PASSWORD '<strong>';            -- what run.bat uses
CREATE ROLE mapinc_report  LOGIN PASSWORD '<strong>';            -- optional read-only reporting

ALTER DATABASE mapinc OWNER TO mapinc_owner;
REVOKE ALL ON DATABASE mapinc FROM PUBLIC;
GRANT CONNECT ON DATABASE mapinc TO mapinc_app, mapinc_report;

-- after `manage.py migrate` has run as mapinc_owner:
GRANT USAGE ON SCHEMA public TO mapinc_app, mapinc_report;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mapinc_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mapinc_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mapinc_report;
ALTER DEFAULT PRIVILEGES FOR ROLE mapinc_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mapinc_app;
ALTER DEFAULT PRIVILEGES FOR ROLE mapinc_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO mapinc_app;

-- the development role created during setup must not exist in production
DROP ROLE IF EXISTS mapinc;   -- (or ALTER ROLE mapinc NOCREATEDB NOLOGIN)
ALTER ROLE postgres PASSWORD '<new strong password>';
```
`mapinc.ini` on the server uses `mapinc_app`; migrations are run by an admin with a
second ini (`mapinc.migrate.ini`) or by temporarily editing the user. The app
change to support `MAPINC_INI` env override is in Phase 3.

**Row-Level Security:** not adopted. RLS partitions rows *between database
roles*; here a single role (`mapinc_app`) serves every staff member, so RLS would
add nothing. Per-user restriction is enforced in the app (Phase 3.4). Document this
decision in the risk analysis.

### 1.2 Authentication and encryption in transit
`postgresql.conf` (`C:\Program Files\PostgreSQL\<ver>\data\`):
```
password_encryption = scram-sha-256
ssl = on
ssl_cert_file = 'server.crt'          # from the internal CA (AD CS) or self-signed for localhost-only
ssl_key_file  = 'server.key'
ssl_min_protocol_version = 'TLSv1.2'
listen_addresses = 'localhost'        # app and DB on the same box → never expose 5432 on the LAN
```
`pg_hba.conf` — replace every `host` line with `hostssl`, SCRAM only, no `trust`:
```
# TYPE   DATABASE  USER           ADDRESS        METHOD
hostssl  mapinc    mapinc_app     127.0.0.1/32   scram-sha-256
hostssl  mapinc    mapinc_owner   127.0.0.1/32   scram-sha-256
hostssl  mapinc    mapinc_report  127.0.0.1/32   scram-sha-256
hostssl  all       postgres       127.0.0.1/32   scram-sha-256
# nothing else — remove the ::1 / 0.0.0.0 defaults the installer added
```
Restart the service, then on the client side set `sslmode = verify-full` (or
`require` with a self-signed cert) in `mapinc.ini` (app change, Phase 3.1).

If the database ever moves to a separate machine: keep `hostssl` only, list that
machine's IP, and open 5432 in Windows Firewall to that IP alone.

### 1.3 Windows Firewall
```powershell
# Postgres: local only (no inbound rule at all); remove the installer's rule if present
Get-NetFirewallRule -DisplayName "*postgres*" | Remove-NetFirewallRule
# App: LAN only, HTTPS only (Phase 4), e.g. 192.168.1.0/24
New-NetFirewallRule -DisplayName "mapinc HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -RemoteAddress 192.168.1.0/24 -Action Allow
# Port 8000 must NOT be reachable from other machines once IIS is in front (Phase 4)
```

### 1.4 Database logging (the realistic Windows option)
`pgAudit` has no supported Windows build from EDB; compiling it on Windows is not
worth the risk on a production box. Use the built-in logger for the database side
and the app audit log (Phase 3.3) for the "who viewed what" side:
```
logging_collector = on
log_destination = 'csvlog'
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d.log'
log_rotation_age = 1d
log_truncate_on_rotation = off
log_connections = on
log_disconnections = on
log_statement = 'ddl'          # every schema change
log_min_duration_statement = -1
log_line_prefix = '%m [%p] user=%u db=%d app=%a host=%h '
```
Deliberately **not** `log_statement = 'all'`: that writes patient data into the log
file (every INSERT/UPDATE with values), which creates a second ePHI store to protect.
Row-level history is captured by the app instead.

## Phase 2 — Encryption at rest and backups (server config, ~half a day)

1. **BitLocker** on every volume holding ePHI: the Postgres data directory, the PDF
   root folder, backup volume, and the OS drive (page file, temp). TPM + PIN or
   TPM + startup key; store recovery keys in AD or a sealed envelope.
   Server 2012 R2 supports BitLocker; enable the feature (`Install-WindowsFeature BitLocker`).
2. **pgcrypto column encryption: not adopted.** The Letters page searches by member
   name and the letter must print the values; encrypting columns would break search
   and add key-management burden without changing who can read the data (the app
   would still decrypt everything). Full-volume encryption is the proportionate
   control here. Document the decision.
3. **Backups**: nightly Task Scheduler job running as a service account:
   ```powershell
   $d = Get-Date -Format yyyyMMdd
   & "C:\Program Files\PostgreSQL\<ver>\bin\pg_dump.exe" -U mapinc_owner -Fc mapinc -f "E:\Backups\mapinc-$d.dump"
   robocopy "\\server\claims" "E:\Backups\claims" /MIR /R:2 /W:5 /LOG+:E:\Backups\claims-$d.log
   ```
   `E:` is BitLocker-encrypted; keep 35 daily + 12 monthly; copy monthly sets
   off-site encrypted (7-Zip AES-256 with a key held by the practice owner, or an
   encrypted drive). **Test a restore quarterly** and record it.
4. **NTFS permissions** on the PDF root: remove `Users`/`Everyone`; grant Modify to a
   `MAP-Clinical` AD group and to the service account that runs `run.bat`.
   Enable file-access auditing on that folder (Object Access audit policy) so
   Windows Security log records who opened which PDF outside the app.

## Phase 3 — Application changes (code, ~2 days)

| # | Change | Why |
|---|---|---|
| 3.1 | `mapinc.ini` gains `[database] sslmode` (default `require`) and `sslrootcert`; `MAPINC_INI` env var selects an alternate ini for migrations | in-transit encryption; separate owner/app roles |
| 3.2 | Security settings when `debug = false`: `SESSION_COOKIE_AGE = 30 min`, `SESSION_EXPIRE_AT_BROWSER_CLOSE`, `SESSION_SAVE_EVERY_REQUEST`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_PROXY_SSL_HEADER`, `SECURE_HSTS_SECONDS`, `X_FRAME_OPTIONS = DENY`, `Cache-Control: no-store` on every letter/list/PDF response | automatic logoff, no ePHI cached on PCs |
| 3.3 | **`AuditEvent` table** — `when, user, windows_user, ip, action, case_encounter, detail` — written for: form opened (prefill), letter created, letter updated, PDF downloaded, PDF regenerated, settings changed, login/logout/failed login. Read-only page under Settings ("Audit log") with date/user filters and CSV export. Rows are insert-only (app role gets no UPDATE/DELETE on this table — Phase 1.1 grant list adjusted) | HIPAA audit controls: who viewed/changed what, when |
| 3.4 | **Identity**: the letter form currently trusts the `user=` value from Access/Outlook. Two options, choose one: (a) IIS Windows Authentication in front (Phase 4) + `RemoteUserMiddleware` → real domain identity, no extra login; (b) require app login on the letter form too. (a) is recommended: single sign-on, and `created_by/modified_by` become verified | access control, non-repudiation |
| 3.5 | Password policy: validators `MinimumLength(12)`, `CommonPassword`, `NumericPassword`, `UserAttributeSimilarity`; `django-axes` lockout after 5 failed logins for 15 minutes; failed logins in the audit log | access control |
| 3.6 | Handoff hardening: TTL 15 → 5 minutes, token invalidated on first successful letter save, nightly purge command; handoff endpoint restricted to LAN subnet (setting) | minimise exposure of the stash |
| 3.7 | Query-string prefill (`?member_name=…`) disabled unless `allow_query_prefill = true` in ini (dev only) | keeps PHI out of URLs/history/logs in production |
| 3.8 | Startup checks (`manage.py check --deploy` + custom): refuse to start with `debug = true`, `secret_key = change-me`, `allowed_hosts = *`, `sslmode = disable`, or the `mapinc` dev role | can't accidentally run an unhardened config |
| 3.9 | Dependency pinning + `pip-audit` in the README's update procedure | patching |

Each item is a normal TDD task in this repo; 3.3 and 3.4 are the larger ones.

## Phase 4 — HTTPS and Windows Authentication with IIS in front (server config, ~1 day)

Waitress speaks plain HTTP. Put IIS in front as a reverse proxy — it is already on
Windows Server, does TLS, and can do Windows Authentication (Kerberos/NTLM).

1. Install IIS + **URL Rewrite** + **Application Request Routing (ARR)**; enable
   proxy in ARR.
2. Certificate: request a server certificate from the domain's AD CS (or import a
   purchased one). Bind HTTPS 443 on a site `mapinc`.
3. Site rules: rewrite `https://letters.map.local/*` → `http://127.0.0.1:8000/*`;
   set `X-Forwarded-Proto: https` (Django trusts it via `SECURE_PROXY_SSL_HEADER`).
4. **Windows Authentication** enabled, Anonymous disabled, on the site; URL Rewrite
   server variable `HTTP_X_REMOTE_USER = {LOGON_USER}` forwarded to Waitress.
   Django: `RemoteUserMiddleware` reading `HTTP_X_REMOTE_USER`, auto-creating users
   (`is_staff` false), so every request is tied to a domain account — no separate
   login for the letter form; the Settings/Letters pages additionally require the
   `MAP-Clinical` group (mapped via `is_staff` set by an admin).
5. Waitress bound to `127.0.0.1:8000` only (`run.bat` change) so nothing bypasses IIS.
6. Launchers: `LETTER_BASE_URL = "https://letters.map.local"`; Edge passes Windows
   credentials automatically to intranet sites (no prompt).
7. `run.bat` installed as a Windows service (NSSM) running as a dedicated
   low-privilege service account that has Word and the PDF share; never as a
   domain admin.

## Phase 5 — Log integrity and retention (~half a day)

- Sources: Postgres csvlog, app `AuditEvent` table (exported nightly to CSV), IIS
  access logs (URLs contain only tokens), Windows Security log (logons, file access
  on the PDF share).
- Forward with **NXLog Community** or **Winlogbeat** to a write-once destination the
  DB admin cannot alter: a separate log server share with append-only ACL, or the
  practice's SIEM if it has one. If neither exists, minimum viable: nightly copy to
  a folder where the service account has *write but not delete/modify* NTFS rights,
  and a monthly hash (`Get-FileHash`) list signed and stored with the compliance
  officer.
- Retention: 6 years (HIPAA documentation rule); Postgres logs 90 days locally.

## Phase 6 — Verification and evidence (~half a day, then recurring)

Checklist run after Phases 1–5 and kept as evidence:

- [ ] `psql -h <server-ip> -U mapinc_app` from another PC **fails** (port closed); from the server, non-SSL connect **fails** (`sslmode=disable`).
- [ ] `SELECT rolsuper, rolcreatedb FROM pg_roles WHERE rolname LIKE 'mapinc%'` → all false.
- [ ] `manage-bde -status` → all ePHI volumes "Fully Encrypted".
- [ ] `http://<server>:8000/` from another PC **fails**; `https://letters.map.local/letter/` works and shows the padlock.
- [ ] Opening the form as a domain user records that user in the audit log; the `user=` parameter is ignored.
- [ ] 5 wrong passwords lock the account; session expires after 30 idle minutes.
- [ ] Generate, view, download a letter → three audit events with correct user/IP.
- [ ] A staff account outside `MAP-Clinical` cannot open Settings/Letters/Audit.
- [ ] `Get-Acl '\\server\claims'` shows only `MAP-Clinical`, the service account, and Administrators.
- [ ] Backup restored onto a scratch database, row counts match; date recorded.
- [ ] Log forwarding: delete a line locally → the forwarded copy is unchanged.
- [ ] Windows Update current; PostgreSQL and Python at supported versions; `pip-audit` clean.

Recurring: monthly patching, quarterly restore test and access review (who is in
`MAP-Clinical`, who has Django `is_staff`), annual re-run of this checklist.

## Decisions and risks to record in the organisation's risk analysis

1. **Windows Server 2012 R2 is end-of-life (Oct 2023).** It no longer receives
   security patches. Every control above still applies, but an unsupported OS is a
   finding in any HIPAA risk analysis. Recommended: migrate the server to Windows
   Server 2019/2022 (the app and Postgres move unchanged) before or shortly after
   go-live; until then, keep it LAN-only behind the firewall and document the
   compensating controls.
2. RLS and pgcrypto not used — rationale above.
3. pgAudit not used on Windows — app-level audit log + Postgres DDL/connection logging instead.
4. No BAA is required for an on-premises database. A BAA **is** required for any
   third party that touches the PDFs or the database: off-site backup providers,
   an IT contractor with admin access, a fax/e-mail service used to send the letters.
5. Microsoft Word on the server runs under the service account; its temp files live
   on the encrypted OS volume.

## Effort summary

| Phase | Owner | Effort |
|---|---|---|
| 1 Database hardening | server admin (with me) | 0.5 day |
| 2 Encryption at rest, backups, NTFS | server admin | 0.5 day + BitLocker encryption time |
| 3 Application changes | me | 2 days |
| 4 IIS HTTPS + Windows auth, service install | server admin (with me) | 1 day |
| 5 Log forwarding & retention | server admin | 0.5 day |
| 6 Verification & evidence | both | 0.5 day |

Suggested order: 3 (so the app is ready for the new roles/SSL/auth) → 1 → 4 → 2 → 5 → 6.
