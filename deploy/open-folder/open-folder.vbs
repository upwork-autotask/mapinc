' Handler for the "mapinc-folder:" URL scheme (see mapinc-folder.reg).
' The browser hands us  mapinc-folder:\\server\claims\SMITH_JOHN  (URL-encoded);
' we decode it and open that folder in Windows Explorer. Nothing else is run:
' the argument must be an existing folder, and it is passed to Explorer as a
' parameter, never to a command interpreter.

Option Explicit

Dim raw, path, fso, shell

If WScript.Arguments.Count = 0 Then WScript.Quit 0
raw = WScript.Arguments(0)

' strip the scheme, tolerate mapinc-folder: and mapinc-folder://
If InStr(LCase(raw), "mapinc-folder:") = 1 Then raw = Mid(raw, Len("mapinc-folder:") + 1)
Do While Left(raw, 1) = "/" And Left(raw, 2) <> "//"
    raw = Mid(raw, 2)
Loop
path = UrlDecode(raw)
path = Replace(path, "/", "\")
If Right(path, 1) = "\" And Len(path) > 3 Then path = Left(path, Len(path) - 1)

Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FolderExists(path) Then
    MsgBox "This folder is not available from this PC:" & vbCrLf & vbCrLf & path, _
           vbExclamation, "MAP Inc - Clinicals Request"
    WScript.Quit 1
End If

Set shell = CreateObject("Shell.Application")
shell.Explore path
WScript.Quit 0

Function UrlDecode(ByVal s)
    Dim i, ch, out
    out = ""
    i = 1
    Do While i <= Len(s)
        ch = Mid(s, i, 1)
        If ch = "%" And i + 2 <= Len(s) Then
            out = out & Chr(CLng("&H" & Mid(s, i + 1, 2)))
            i = i + 3
        ElseIf ch = "+" Then
            out = out & " "
            i = i + 1
        Else
            out = out & ch
            i = i + 1
        End If
    Loop
    UrlDecode = out
End Function
