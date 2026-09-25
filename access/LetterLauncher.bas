Attribute VB_Name = "LetterLauncher"
Option Compare Database
Option Explicit

' ---------------------------------------------------------------------------
' MAP Inc "Clinicals Request" launcher for MS Access.
'
' Install: VBA editor > File > Import File... > this .bas file, then set
' LETTER_BASE_URL below. From a button on your case form call:
'
'   OpenClinicalsLetterDialog Me.CaseEncounter, Me.PolicyID, Me.MemberName, Me.DOB, Me.Admission, Me.FolderPath
'
' caseLocation and caseType are optional; they are stored with the letter and
' can appear in the PDF file name (Settings > PDF filename pattern).
'
' The last argument is the WHOLE destination folder, e.g. \\server\claims\SMITH_JOHN.
' The letter (.pdf and .docx) is written into it; the web form shows it read-only.
'
' For a TRUE Access modal dialog (Microsoft 365 Access, build 2303 or newer),
' see OpenClinicalsLetterInAccessForm at the bottom of this module.
'
' How it works: the values are POSTed to the server, which answers with a
' short-lived link (…/letter/?t=<token>) — so no patient data ever appears in
' a URL, window title or browser history. That link is opened in a NEW,
' chromeless Edge window sized like a dialog. OpenClinicalsLetterDialog waits
' until that window is closed; OpenClinicalsLetter returns immediately.
' ---------------------------------------------------------------------------

Private Const LETTER_BASE_URL As String = "http://SERVER-NAME:8000"   ' <-- server running run.bat

' Dialog size in pixels (the web form is 480px wide)
Private Const DIALOG_WIDTH As Long = 560
Private Const DIALOG_HEIGHT As Long = 720

#If VBA7 Then
    Private Declare PtrSafe Function OpenProcess Lib "kernel32" (ByVal dwDesiredAccess As Long, ByVal bInheritHandle As Long, ByVal dwProcessId As Long) As LongPtr
    Private Declare PtrSafe Function WaitForSingleObject Lib "kernel32" (ByVal hHandle As LongPtr, ByVal dwMilliseconds As Long) As Long
    Private Declare PtrSafe Function CloseHandle Lib "kernel32" (ByVal hObject As LongPtr) As Long
    Private Declare PtrSafe Function GetSystemMetrics Lib "user32" (ByVal nIndex As Long) As Long
    Private Declare PtrSafe Function ShellExecuteW Lib "shell32" (ByVal hwnd As LongPtr, ByVal lpOperation As LongPtr, ByVal lpFile As LongPtr, ByVal lpParameters As LongPtr, ByVal lpDirectory As LongPtr, ByVal nShowCmd As Long) As LongPtr
#Else
    Private Declare Function OpenProcess Lib "kernel32" (ByVal dwDesiredAccess As Long, ByVal bInheritHandle As Long, ByVal dwProcessId As Long) As Long
    Private Declare Function WaitForSingleObject Lib "kernel32" (ByVal hHandle As Long, ByVal dwMilliseconds As Long) As Long
    Private Declare Function CloseHandle Lib "kernel32" (ByVal hObject As Long) As Long
    Private Declare Function GetSystemMetrics Lib "user32" (ByVal nIndex As Long) As Long
    Private Declare Function ShellExecuteW Lib "shell32" (ByVal hwnd As Long, ByVal lpOperation As Long, ByVal lpFile As Long, ByVal lpParameters As Long, ByVal lpDirectory As Long, ByVal nShowCmd As Long) As Long
#End If

Private Const SYNCHRONIZE As Long = &H100000
Private Const WAIT_TIMEOUT As Long = &H102
Private Const SM_CXSCREEN As Long = 0
Private Const SM_CYSCREEN As Long = 1
Private Const SW_SHOWNORMAL As Long = 1

' ===========================================================================
' Public entry points
' ===========================================================================

' Example macro for a ribbon button: asks for the values, then opens the dialog.
Public Sub OpenLetterFromPrompt()
    Dim caseEncounter As String, policyId As String, memberName As String
    Dim dob As String, admission As String, folderName As String
    Dim caseLocation As String, caseType As String
    caseEncounter = InputBox("Case / Encounter number:", "Clinicals Request")
    If Len(caseEncounter) = 0 Then Exit Sub
    policyId = InputBox("Policy ID No.:", "Clinicals Request")
    memberName = InputBox("Member name:", "Clinicals Request")
    dob = InputBox("Date of birth (m/d/yyyy):", "Clinicals Request")
    admission = InputBox("Admission (date or status):", "Clinicals Request")
    folderName = InputBox("Destination folder (full path):", "Clinicals Request")
    caseLocation = InputBox("Case location (optional, used in the file name):", "Clinicals Request")
    caseType = InputBox("Case type (optional, used in the file name):", "Clinicals Request")
    OpenClinicalsLetterDialog caseEncounter, policyId, memberName, dob, admission, folderName, _
                              caseLocation, caseType
End Sub

' Opens the letter form in a new dialog-sized window and waits until it is closed.
Public Sub OpenClinicalsLetterDialog(ByVal caseEncounter As Variant, ByVal policyId As Variant, _
                                     ByVal memberName As Variant, ByVal dob As Variant, _
                                     ByVal admission As Variant, ByVal folderName As Variant, _
                                     Optional ByVal caseLocation As Variant = "", _
                                     Optional ByVal caseType As Variant = "")
    Dim url As String, pid As Double
    url = RequestHandoffUrl(caseEncounter, policyId, memberName, dob, admission, folderName, caseLocation, caseType)
    If Len(url) = 0 Then Exit Sub
    pid = LaunchDialogWindow(url)
    If pid > 0 Then WaitForProcess pid
End Sub

' Opens the letter form in a new dialog-sized window and returns immediately.
Public Sub OpenClinicalsLetter(ByVal caseEncounter As Variant, ByVal policyId As Variant, _
                               ByVal memberName As Variant, ByVal dob As Variant, _
                               ByVal admission As Variant, ByVal folderName As Variant, _
                               Optional ByVal caseLocation As Variant = "", _
                               Optional ByVal caseType As Variant = "")
    Dim url As String
    url = RequestHandoffUrl(caseEncounter, policyId, memberName, dob, admission, folderName, caseLocation, caseType)
    If Len(url) > 0 Then LaunchDialogWindow url
End Sub

' ===========================================================================
' Hand the values to the server; get back a token link
' ===========================================================================

Private Function RequestHandoffUrl(ByVal caseEncounter As Variant, ByVal policyId As Variant, _
                                   ByVal memberName As Variant, ByVal dob As Variant, _
                                   ByVal admission As Variant, ByVal folderName As Variant, _
                                   Optional ByVal caseLocation As Variant = "", _
                                   Optional ByVal caseType As Variant = "") As String
    Dim http As Object, body As String
    body = "case_encounter=" & UrlEnc(NzS(caseEncounter)) & _
           "&policy_id=" & UrlEnc(NzS(policyId)) & _
           "&member_name=" & UrlEnc(NzS(memberName)) & _
           "&dob=" & UrlEnc(FormatDob(dob)) & _
           "&admission=" & UrlEnc(NzS(admission)) & _
           "&folder_name=" & UrlEnc(NzS(folderName)) & _
           "&case_location=" & UrlEnc(NzS(caseLocation)) & _
           "&case_type=" & UrlEnc(NzS(caseType)) & _
           "&user=" & UrlEnc(Environ("USERNAME"))
    On Error GoTo Failed
    Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
    http.SetTimeouts 5000, 5000, 10000, 10000
    http.Open "POST", LETTER_BASE_URL & "/letter/handoff/", False
    http.SetRequestHeader "Content-Type", "application/x-www-form-urlencoded"
    http.Send body
    If http.Status = 200 Then
        RequestHandoffUrl = Trim$(http.ResponseText)
        Exit Function
    End If
    MsgBox "The letter server answered HTTP " & http.Status & " (" & http.StatusText & ").", vbExclamation, "Clinicals Request"
    Exit Function
Failed:
    MsgBox "Cannot reach the letter server at " & LETTER_BASE_URL & vbCrLf & vbCrLf & _
           "Make sure run.bat is running on the server and the address in LETTER_BASE_URL is correct." & _
           vbCrLf & vbCrLf & Err.Description, vbExclamation, "Clinicals Request"
End Function

' ===========================================================================
' Dialog-style browser window
' ===========================================================================

' Opens the URL in a NEW, chromeless (no address bar / tabs) window, sized and
' centred like a dialog. Uses Edge, else Chrome; falls back to the default
' browser if neither is installed. Returns the process id, or 0.
Private Function LaunchDialogWindow(ByVal url As String) As Double
    Dim browser As String, profile As String, cmd As String, x As Long, y As Long
    browser = FindBrowser()
    If Len(browser) = 0 Then
        ShellExecuteW 0, StrPtr("open"), StrPtr(url), 0, 0, SW_SHOWNORMAL
        Exit Function
    End If
    ' A private profile keeps the window in its own process (so we can wait for it)
    profile = Environ("LOCALAPPDATA") & "\MapInc\LetterDialogProfile"
    x = (GetSystemMetrics(SM_CXSCREEN) - DIALOG_WIDTH) \ 2
    y = (GetSystemMetrics(SM_CYSCREEN) - DIALOG_HEIGHT) \ 2
    If x < 0 Then x = 0
    If y < 0 Then y = 0
    cmd = """" & browser & """ --new-window --app=""" & url & """" & _
          " --window-size=" & DIALOG_WIDTH & "," & DIALOG_HEIGHT & _
          " --window-position=" & x & "," & y & _
          " --user-data-dir=""" & profile & """ --no-first-run --no-default-browser-check"
    LaunchDialogWindow = Shell(cmd, vbNormalFocus)
End Function

' Edge (registry App Paths, then the usual folders), then Chrome.
Private Function FindBrowser() As String
    Dim candidates As Variant, i As Integer, p As String
    p = RegReadSafe("HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe\")
    If Len(p) > 0 Then If Len(Dir(p)) > 0 Then FindBrowser = p: Exit Function
    candidates = Array("C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", _
                       "C:\Program Files\Microsoft\Edge\Application\msedge.exe", _
                       Environ("LOCALAPPDATA") & "\Microsoft\Edge\Application\msedge.exe", _
                       "C:\Program Files\Google\Chrome\Application\chrome.exe", _
                       "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", _
                       Environ("LOCALAPPDATA") & "\Google\Chrome\Application\chrome.exe")
    For i = LBound(candidates) To UBound(candidates)
        If Len(Dir(candidates(i))) > 0 Then FindBrowser = candidates(i): Exit Function
    Next i
End Function

Private Function RegReadSafe(ByVal key As String) As String
    On Error Resume Next
    RegReadSafe = CreateObject("WScript.Shell").RegRead(key)
End Function

' Blocks (while keeping Access responsive) until the process exits.
Private Sub WaitForProcess(ByVal pid As Double)
    #If VBA7 Then
        Dim h As LongPtr
    #Else
        Dim h As Long
    #End If
    h = OpenProcess(SYNCHRONIZE, 0, CLng(pid))
    If h = 0 Then Exit Sub
    Do While WaitForSingleObject(h, 100) = WAIT_TIMEOUT
        DoEvents
    Loop
    CloseHandle h
End Sub

' ===========================================================================
' Helpers
' ===========================================================================

' Null/Empty-safe string (replacement for Access's Nz).
Private Function NzS(ByVal v As Variant) As String
    If IsNull(v) Or IsEmpty(v) Or IsMissing(v) Then
        NzS = ""
    Else
        NzS = Trim$(CStr(v))
    End If
End Function

Private Function FormatDob(ByVal dob As Variant) As String
    If IsDate(dob) Then
        FormatDob = Format(CDate(dob), "yyyy-mm-dd")
    Else
        FormatDob = NzS(dob)
    End If
End Function

' Percent-encodes a string as UTF-8 for use in a query string / form body.
Public Function UrlEnc(ByVal s As String) As String
    Dim bytes() As Byte, i As Long, out As String
    If Len(s) = 0 Then Exit Function
    bytes = Utf8Bytes(s)
    For i = LBound(bytes) To UBound(bytes)
        Select Case bytes(i)
            Case 48 To 57, 65 To 90, 97 To 122, 45, 46, 95, 126   ' 0-9 A-Z a-z - . _ ~
                out = out & Chr(bytes(i))
            Case Else
                out = out & "%" & Right("0" & Hex(bytes(i)), 2)
        End Select
    Next i
    UrlEnc = out
End Function

Private Function Utf8Bytes(ByVal s As String) As Byte()
    Dim stm As Object
    Set stm = CreateObject("ADODB.Stream")
    stm.Type = 2            ' text
    stm.Charset = "utf-8"
    stm.Open
    stm.WriteText s
    stm.Position = 0
    stm.Type = 1            ' binary
    stm.Position = 3        ' skip the UTF-8 BOM
    Utf8Bytes = stm.Read
    stm.Close
End Function

' ===========================================================================
' Alternative: a real Access modal dialog form (Microsoft 365 Access 2303+)
' ===========================================================================
'
' 1. Create a blank form named frmLetterDialog. Properties:
'       Pop Up = Yes, Modal = Yes, Border Style = Dialog, Auto Center = Yes,
'       Record Selectors = No, Navigation Buttons = No, Scroll Bars = Neither,
'       Width about 9 cm / 3.6 in, Detail height about 12 cm / 4.8 in.
' 2. Add an "Edge Browser Control" (Design > Controls) named webLetter,
'    sized to fill the form, Horizontal/Vertical Anchor = Both.
' 3. Add a command button named cmdClose with caption "Close".
' 4. Paste this into the form's code module:
'
'       Option Compare Database
'       Option Explicit
'
'       Private Sub Form_Open(Cancel As Integer)
'           If Len(Me.OpenArgs & "") = 0 Then Cancel = True: Exit Sub
'           Me.webLetter.Navigate Me.OpenArgs
'       End Sub
'
'       Private Sub cmdClose_Click()
'           DoCmd.Close acForm, Me.Name
'       End Sub
'
' 5. Open it from your case form with the procedure below. acDialog makes
'    Access wait until the form is closed.

Public Sub OpenClinicalsLetterInAccessForm(ByVal caseEncounter As Variant, ByVal policyId As Variant, _
                                           ByVal memberName As Variant, ByVal dob As Variant, _
                                           ByVal admission As Variant, ByVal folderName As Variant)
    Dim url As String
    url = RequestHandoffUrl(caseEncounter, policyId, memberName, dob, admission, folderName, caseLocation, caseType)
    If Len(url) > 0 Then DoCmd.OpenForm "frmLetterDialog", acNormal, , , , acDialog, url
End Sub
