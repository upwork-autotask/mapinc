<#
Phase 1.3 + 2.4 — Windows Firewall and NTFS permissions.
Run in an elevated PowerShell on the server.

  .\03-firewall-and-folders.ps1 -LanSubnet 192.168.1.0/24 -PdfRoot "D:\claims" -ClinicalGroup "MAP\MAP-Clinical" -ServiceAccount "MAP\svc-mapinc"
#>
param(
    [Parameter(Mandatory)] [string]$LanSubnet,
    [Parameter(Mandatory)] [string]$PdfRoot,
    [Parameter(Mandatory)] [string]$ClinicalGroup,
    [Parameter(Mandatory)] [string]$ServiceAccount
)
$ErrorActionPreference = "Stop"

# --- Firewall -----------------------------------------------------------------
# PostgreSQL: no inbound rule at all (it listens on localhost only after step 02).
Get-NetFirewallRule -DisplayName "*postgres*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
# HTTPS from the LAN only (IIS in front of the app, see 04-iis).
Get-NetFirewallRule -DisplayName "mapinc HTTPS" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "mapinc HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 `
    -RemoteAddress $LanSubnet -Action Allow | Out-Null
# Port 8000 (Waitress) must never be reachable from other machines.
Get-NetFirewallRule -DisplayName "mapinc HTTP 8000*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "mapinc HTTP 8000 block" -Direction Inbound -Protocol TCP -LocalPort 8000 `
    -Action Block | Out-Null

# --- PDF root folder ACL ------------------------------------------------------
if (-not (Test-Path $PdfRoot)) { New-Item -ItemType Directory -Path $PdfRoot | Out-Null }
icacls $PdfRoot /inheritance:r `
    /grant:r "BUILTIN\Administrators:(OI)(CI)F" `
    /grant:r "SYSTEM:(OI)(CI)F" `
    /grant:r "${ClinicalGroup}:(OI)(CI)M" `
    /grant:r "${ServiceAccount}:(OI)(CI)M" | Out-Null
# Audit file access (needs "Audit object access" enabled in Local/Group Policy).
$acl = Get-Acl $PdfRoot
$rule = New-Object System.Security.AccessControl.FileSystemAuditRule(
    "Everyone", "ReadData,WriteData,Delete", "ContainerInherit,ObjectInherit", "None", "Success")
$acl.AddAuditRule($rule)
Set-Acl $PdfRoot $acl
auditpol /set /subcategory:"File System" /success:enable /failure:enable | Out-Null

Write-Host "Firewall rules and ACLs applied."
Get-NetFirewallRule -DisplayName "mapinc*" | Format-Table DisplayName, Direction, Action
icacls $PdfRoot
