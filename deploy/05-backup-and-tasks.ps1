<#
Phase 2.3 + 3.6 — nightly encrypted-volume backup and housekeeping tasks.
Run once, elevated, on the server:

  .\05-backup-and-tasks.ps1 -RepoDir "C:\mapinc" -BackupDir "E:\Backups" -PdfRoot "D:\claims" -PgVersion 18 -ServiceAccount "MAP\svc-mapinc"

E: must be a BitLocker-encrypted volume. The service account needs the
mapinc_owner password in a .pgpass file:  %APPDATA%\postgresql\pgpass.conf
containing   localhost:5432:mapinc:mapinc_owner:<password>
#>
param(
    [Parameter(Mandatory)] [string]$RepoDir,
    [Parameter(Mandatory)] [string]$BackupDir,
    [Parameter(Mandatory)] [string]$PdfRoot,
    [string]$PgVersion = "18",
    [Parameter(Mandatory)] [string]$ServiceAccount
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force "$BackupDir\db", "$BackupDir\claims", "$BackupDir\logs" | Out-Null

# --- backup script ------------------------------------------------------------
$backup = @"
`$d = Get-Date -Format yyyyMMdd
`$log = "$BackupDir\logs\backup-`$d.log"
& "C:\Program Files\PostgreSQL\$PgVersion\bin\pg_dump.exe" -h localhost -U mapinc_owner -w -Fc mapinc -f "$BackupDir\db\mapinc-`$d.dump" 2>> `$log
if (`$LASTEXITCODE -ne 0) { "pg_dump FAILED" >> `$log; exit 1 }
robocopy "$PdfRoot" "$BackupDir\claims" /MIR /R:2 /W:5 /NP /LOG+:`$log | Out-Null
# retention: 35 daily dumps; keep the 1st of each month for 12 months
Get-ChildItem "$BackupDir\db\mapinc-*.dump" | Where-Object { `$_.LastWriteTime -lt (Get-Date).AddDays(-35) -and `$_.Name -notmatch '\d{6}01\.dump$' } | Remove-Item
Get-ChildItem "$BackupDir\db\mapinc-*01.dump" | Where-Object { `$_.LastWriteTime -lt (Get-Date).AddDays(-366) } | Remove-Item
"OK `$(Get-Date)" >> `$log
"@
$backupPath = "$BackupDir\mapinc-backup.ps1"
Set-Content $backupPath $backup -Encoding utf8

# --- scheduled tasks ----------------------------------------------------------
$cred = Get-Credential -UserName $ServiceAccount -Message "Password for $ServiceAccount (runs the tasks)"
$pw = $cred.GetNetworkCredential().Password

Register-ScheduledTask -TaskName "mapinc nightly backup" -Force `
    -Action (New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$backupPath`"") `
    -Trigger (New-ScheduledTaskTrigger -Daily -At 01:30) `
    -User $ServiceAccount -Password $pw -RunLevel Highest | Out-Null

Register-ScheduledTask -TaskName "mapinc purge handoff tokens" -Force `
    -Action (New-ScheduledTaskAction -Execute "$RepoDir\.venv\Scripts\python.exe" -Argument "manage.py purge_handoffs" -WorkingDirectory $RepoDir) `
    -Trigger (New-ScheduledTaskTrigger -Daily -At 02:00) `
    -User $ServiceAccount -Password $pw | Out-Null

Write-Host "Tasks registered. Test now with:  Start-ScheduledTask 'mapinc nightly backup'; Get-Content $BackupDir\logs\backup-*.log"
Write-Host "Quarterly: restore a dump into a scratch database and record the result:"
Write-Host "  createdb -U postgres mapinc_restore_test; pg_restore -U postgres -d mapinc_restore_test <dump>; psql -c 'select count(*) from letters_letter' mapinc_restore_test"
