<#
Phase 4.7 — run the app as a Windows service under a low-privilege account (NSSM).
Run elevated:

  .\06-install-service.ps1 -RepoDir "C:\mapinc" -ServiceAccount "MAP\svc-mapinc"

Prerequisites: NSSM (https://nssm.cc) on the PATH or in C:\tools\nssm; the
service account has Word installed/activated in its profile (log on once
interactively and open Word), Modify on the PDF root, and read on the repo.
#>
param(
    [Parameter(Mandatory)] [string]$RepoDir,
    [Parameter(Mandatory)] [string]$ServiceAccount,
    [string]$Listen = "127.0.0.1:8000"
)
$ErrorActionPreference = "Stop"
$nssm = (Get-Command nssm.exe -ErrorAction SilentlyContinue).Source
if (-not $nssm) { $nssm = "C:\tools\nssm\nssm.exe" }
if (-not (Test-Path $nssm)) { throw "nssm.exe not found - install NSSM first" }

$cred = Get-Credential -UserName $ServiceAccount -Message "Password for $ServiceAccount"
$pw = $cred.GetNetworkCredential().Password
$logDir = "$RepoDir\logs"; New-Item -ItemType Directory -Force $logDir | Out-Null

& $nssm stop MapIncLetters 2>$null
& $nssm remove MapIncLetters confirm 2>$null
& $nssm install MapIncLetters "$RepoDir\run.bat"
& $nssm set MapIncLetters AppDirectory $RepoDir
& $nssm set MapIncLetters AppEnvironmentExtra "MAPINC_LISTEN=$Listen"
& $nssm set MapIncLetters AppStdout "$logDir\service.log"
& $nssm set MapIncLetters AppStderr "$logDir\service.log"
& $nssm set MapIncLetters AppRotateFiles 1
& $nssm set MapIncLetters AppRotateBytes 10485760
& $nssm set MapIncLetters ObjectName $ServiceAccount $pw
& $nssm set MapIncLetters Start SERVICE_AUTO_START
& $nssm set MapIncLetters Description "MAP Inc Clinicals Request letter service (Waitress on $Listen)"
& $nssm start MapIncLetters

# The service account must not be able to change the code or config.
icacls $RepoDir /grant:r "${ServiceAccount}:(OI)(CI)RX" | Out-Null
icacls "$RepoDir\logs" /grant:r "${ServiceAccount}:(OI)(CI)M" | Out-Null
icacls "$RepoDir\media" /grant:r "${ServiceAccount}:(OI)(CI)M" | Out-Null

Start-Sleep 5
Get-Service MapIncLetters
Get-Content "$logDir\service.log" -Tail 5
