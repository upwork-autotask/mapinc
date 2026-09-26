# "Open folder" from a staff PC

Browsers refuse to follow `file://` links from a web page, so the button works
in three steps, stopping at the first that succeeds:

1. **The server opens Explorer** — only when the browser is on the machine that
   runs the app (the request comes from `127.0.0.1`). This needs no setup and
   covers a single-PC install and anyone working on the server itself.
   Switch it off with `MAPINC_LOCAL_EXPLORER=false`.
2. **A URL-protocol handler on the PC** — the files in this folder. Install them
   once per PC and remote browsers can open the folder too.
3. **The clipboard** — the path is copied and the page says so, which always works.

## Installing the handler (step 2)

On each staff PC, or through Group Policy:

```powershell
New-Item -ItemType Directory -Force "C:\Program Files\MapInc" | Out-Null
Copy-Item .\open-folder.vbs "C:\Program Files\MapInc\open-folder.vbs"
reg import .\mapinc-folder.reg          # writes to HKEY_CURRENT_USER, no admin rights needed
```

Then on the server, in `.env`:

```
MAPINC_FOLDER_PROTOCOL=mapinc-folder
```

and restart the app. The first click shows Edge's "Open MapInc folder?" prompt;
ticking **Always allow** makes it silent from then on.

## Checking it

- On the server: open a letter, click **Open folder** → Explorer opens there.
- On a staff PC with the handler: the same click opens Explorer on that PC.
- On a staff PC without it: the page says "Folder path copied — paste it into
  File Explorer."

## What the handler will and will not do

`open-folder.vbs` decodes the path, checks it is an existing folder and hands it
to Explorer. It never passes anything to a command interpreter, and it shows a
message instead of failing silently when the share is not reachable from that PC.
