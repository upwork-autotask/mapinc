# Phase 4 — IIS in front of the app: HTTPS + Windows Authentication

Result: staff open `https://letters.<domain>/letter/…`, IIS checks their Windows
logon (no password prompt on domain PCs), terminates TLS, and forwards to
Waitress on `127.0.0.1:8000` with `X-Remote-User` and `X-Forwarded-Proto`.
The app runs with `auth_mode = remote_user`, so every letter is tied to the
verified domain account.

## 1. Install IIS and the two modules (elevated PowerShell)
```powershell
Install-WindowsFeature Web-Server, Web-Windows-Auth, Web-Mgmt-Console
# URL Rewrite 2.1 and Application Request Routing 3.0 — download from
#   https://www.iis.net/downloads/microsoft/url-rewrite
#   https://www.iis.net/downloads/microsoft/application-request-routing
# then enable the proxy:
& "$env:windir\system32\inetsrv\appcmd.exe" set config -section:system.webServer/proxy /enabled:"True" /preserveHostHeader:"True" /commit:apphost
```

## 2. Allow the server variables the rewrite rule sets and unlock the auth sections
```powershell
$appcmd = "$env:windir\system32\inetsrv\appcmd.exe"
& $appcmd set config -section:system.webServer/rewrite/allowedServerVariables /+"[name='HTTP_X_FORWARDED_PROTO']" /commit:apphost
& $appcmd set config -section:system.webServer/rewrite/allowedServerVariables /+"[name='HTTP_X_REMOTE_USER']" /commit:apphost
& $appcmd unlock config -section:system.webServer/security/authentication/windowsAuthentication
& $appcmd unlock config -section:system.webServer/security/authentication/anonymousAuthentication
```

## 3. Certificate and site
- Request a web-server certificate for `letters.<domain>` from the domain CA
  (Certificates MMC → Personal → Request New Certificate), or import a purchased one.
- Create a DNS A record `letters.<domain>` → server IP.
```powershell
New-Item -ItemType Directory C:\inetpub\mapinc -Force | Out-Null
Copy-Item .\web.config C:\inetpub\mapinc\web.config
Import-Module WebAdministration
New-Website -Name mapinc -PhysicalPath C:\inetpub\mapinc -Port 443 -Ssl -HostHeader "letters.<domain>"
# bind the certificate: IIS Manager → Sites → mapinc → Bindings → https → select certificate
Remove-Website -Name "Default Web Site"   # nothing else should answer on this box
```

## 4. Point the app at IIS
`mapinc.ini` (see `deploy\mapinc.ini.production`):
```
production = true
https = true
behind_proxy = true
auth_mode = remote_user
allowed_hosts = letters.<domain>
```
Waitress must listen on localhost only: set the environment variable
`MAPINC_LISTEN=127.0.0.1:8000` for the service (NSSM → Environment) or before
`run.bat`. Restart the app.

## 5. Launchers
Set `LETTER_BASE_URL = "https://letters.<domain>"` in the Access/Outlook module.
Edge/Chrome send Windows credentials automatically to intranet-zone sites; if the
site is not recognised as intranet, add `https://letters.<domain>` to
*Internet Options → Security → Local intranet → Sites* (or push via GPO).

## 6. Verify
- Browser on a domain PC: `https://letters.<domain>/letter/` shows the padlock and,
  when logged in, the user name (not a Login button) in the title bar.
- `https://letters.<domain>/settings/` → 403 "Not permitted" until an admin sets
  *Staff status* for that user in `/admin/auth/user/`.
- `http://<server-ip>:8000/` from another PC → connection refused.
- Audit log rows show `user = jdoe` and the PC's IP (from `X-Forwarded-For`).
