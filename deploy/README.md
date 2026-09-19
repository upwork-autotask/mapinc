# Production deployment (HIPAA hardening)

Scripts for the server-side phases of `docs/hipaa-hardening-plan.md`. Run them
in order, elevated, on the on-premises server. The application-side changes
(audit log, auth modes, lockout, hardened sessions, handoff tokens, startup
checks) are already in the code and switched on by `MAPINC_PRODUCTION=true` in
`.env`.

| Step | Script | What it does |
|---|---|---|
| 1 | `01-database-roles.sql` | Creates `mapinc_owner` / `mapinc_app` / `mapinc_report`, grants least privilege, makes the audit table insert-only, drops the dev role |
| 2 | `02-postgresql-hardening.ps1` | SCRAM passwords, TLS-only connections from localhost, DDL/connection logging (no statement values in logs) |
| 3 | `03-firewall-and-folders.ps1` | Firewall: 443 from the LAN only, 8000 blocked, no Postgres rule; NTFS ACL + file auditing on the PDF root |
| 4 | `04-iis/` | IIS reverse proxy: HTTPS certificate, Windows Authentication → `X-Remote-User` |
| 5 | `05-backup-and-tasks.ps1` | Nightly `pg_dump` + `robocopy` to an encrypted volume with retention; nightly handoff-token purge |
| 6 | `06-install-service.ps1` | Runs `run.bat` as a Windows service under a low-privilege account, bound to `127.0.0.1:8000` |

Config templates: `env.production` (app role → `.env`) and
`env.migrate.production` (owner role → `.env.migrate`, used via `MAPINC_ENV_FILE`
for `manage.py migrate` only).

## Order of operations on go-live

```powershell
cd C:\mapinc
git pull
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 1. roles (edit the passwords in the file first)
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -d mapinc -f deploy\01-database-roles.sql

# 2. config files
Copy-Item deploy\env.production .env                   # edit CHANGE-ME values
Copy-Item deploy\env.migrate.production .env.migrate   # edit; Administrators-only ACL
icacls .env /inheritance:r /grant:r "BUILTIN\Administrators:F" "SYSTEM:F" "MAP\svc-mapinc:R"
icacls .env.migrate /inheritance:r /grant:r "BUILTIN\Administrators:F" "SYSTEM:F"

# 3. postgres TLS/SCRAM (re-enters the role passwords so they are stored as SCRAM)
.\deploy\02-postgresql-hardening.ps1 -PgVersion 18

# 4. migrate as the owner role, then confirm the config passes the checks
$env:MAPINC_ENV_FILE = "C:\mapinc\.env.migrate"; python manage.py migrate; Remove-Item Env:MAPINC_ENV_FILE
python manage.py check

# 5. firewall, folders, IIS, backups, service
.\deploy\03-firewall-and-folders.ps1 -LanSubnet 192.168.1.0/24 -PdfRoot D:\claims -ClinicalGroup "MAP\MAP-Clinical" -ServiceAccount "MAP\svc-mapinc"
#   follow deploy\04-iis\README.md
.\deploy\05-backup-and-tasks.ps1 -RepoDir C:\mapinc -BackupDir E:\Backups -PdfRoot D:\claims -ServiceAccount "MAP\svc-mapinc"
.\deploy\06-install-service.ps1 -RepoDir C:\mapinc -ServiceAccount "MAP\svc-mapinc"
```

Then run the verification checklist in `docs/hipaa-hardening-plan.md` §6 and keep
the output as evidence.

## BitLocker (Phase 2.1) — not scripted
Enable in Control Panel → BitLocker Drive Encryption (or `Enable-BitLocker`) on
the OS drive, the PostgreSQL data drive, the PDF root drive and the backup drive.
Store recovery keys in Active Directory or with the compliance officer.
`manage-bde -status` must show *Fully Encrypted* for each.

## Log forwarding (Phase 5) — site-specific
Sources: `C:\Program Files\PostgreSQL\18\data\log\*.csv`, the app's Audit CSV
export (or the `letters_auditevent` table), IIS logs
(`C:\inetpub\logs\LogFiles`), Windows Security log. Forward with NXLog Community
or Winlogbeat to the practice's SIEM, or at minimum to an append-only share on a
different machine; retain 6 years.
