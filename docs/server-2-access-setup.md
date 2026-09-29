# Server 2 Access Setup

This guide lets the client server access the MAP Inc letter app running on the
hosted server.

## Network Details

- Hosted server: `192.168.0.25`
- Client server / Server 2: `192.168.0.244`
- App port: `8000`
- App URL from Server 2: `http://192.168.0.25:8000`

## 1. Start The App On The Hosted Server

On `192.168.0.25`, start the app with `run.bat`.

The app should bind to all interfaces:

```cmd
0.0.0.0:8000
```

`run.bat` already does this by default unless `MAPINC_LISTEN` is set.

If `.env` contains `MAPINC_LISTEN`, make sure it is either removed or set to:

```env
MAPINC_LISTEN=0.0.0.0:8000
```

Do not use this for direct Server 2 access:

```env
MAPINC_LISTEN=127.0.0.1:8000
```

That binds the app to localhost only.

## 2. Configure Django Hosts And Handoff Access

In the hosted server `.env`, use:

```env
MAPINC_ALLOWED_HOSTS=192.168.0.25,localhost,127.0.0.1
MAPINC_HANDOFF_ALLOWED_NETWORKS=127.0.0.1/32,192.168.0.25/32,192.168.0.244/32
```

Restart the app after changing `.env`.

## 3. Allow Only Server 2 Through Windows Firewall

Run this on the hosted server `192.168.0.25` from an Administrator CMD:

```cmd
netsh advfirewall firewall add rule name="Allow MAP Inc 8000 From Server 2" dir=in action=allow protocol=TCP localport=8000 remoteip=192.168.0.244
```

If there is an older broad allow rule for port `8000`, remove or disable it so
the app is not open to the whole LAN.

Check matching rules:

```cmd
netsh advfirewall firewall show rule name=all | findstr /i "8000"
```

## 4. Test From Server 2

On `192.168.0.244`, open:

```text
http://192.168.0.25:8000
```

The letter form should open at:

```text
http://192.168.0.25:8000/letter/
```

## 5. Access / Outlook VBA

The launcher modules are already configured to call:

```text
http://192.168.0.25:8000
```

Files:

- `access/LetterLauncher.bas`
- `outlook/LetterLauncher_Outlook.bas`

Import the updated module into Access or Outlook after deployment.

