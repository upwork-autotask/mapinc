Attribute VB_Name = "LetterLauncher"
Option Compare Database
Option Explicit

' ---------------------------------------------------------------------------
' MAP Inc "Clinicals Request" launcher for MS Access.
'
' Import this module (File > Import in the VBA editor), set LETTER_BASE_URL,
' then from a button on your case form call ONE of:
'
'   OpenClinicalsLetterDialog Me.CaseEncounter, Me.PolicyID, Me.MemberName, Me.DOB, Me.Admission, Me.FolderName
'       Opens a chromeless Edge window sized like a dialog and WAITS until the
'       user closes it, so the code after the call runs when the letter is done.
'
'   OpenClinicalsLetter Me.CaseEncounter, Me.PolicyID, Me.MemberName, Me.DOB, Me.Admission, Me.FolderName
'       Same window, but returns immediately (non-blocking).
'
'   For a TRUE Access modal dialog (Microsoft 365 Access, build 2303 or newer),
'   see OpenClinicalsLetterInAccessForm at the bottom of this module.
'
' The folder name is the sub-folder under the PDF root configured in the web
' app's Settings page. The Windows user name is sent automatically.
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
#Else
    Private Declare Function OpenProcess Lib "kernel32" (ByVal dwDesiredAccess As Long, ByVal bInheritHandle As Long, ByVal dwProcessId As Long) As Long
    Private Declare Function WaitForSingleObject Lib "kernel32" (ByVal hHandle As Long, ByVal dwMilliseconds As Long) As Long
    Private Declare Function CloseHandle Lib "kernel32" (ByVal hObject As Long) As Long
    Private Declare Function GetSystemMetrics Lib "user32" (ByVal nIndex As Long) As Long
#End If

Private Const SYNCHRONIZE As Long = &H100000
Private Const WAIT_TIMEOUT As Long = &H102
Private Const SM_CXSCREEN As Long = 0
Private Const SM_CYSCREEN As Long = 1

' ===========================================================================
' Public entry points
' ===========================================================================

' Opens the letter form in a dialog-sized Edge window and waits until it is closed.
Public Sub OpenClinicalsLetterDialog(ByVal caseEncounter As Variant, ByVal policyId As Variant, _
                                     ByVal memberName As Variant, ByVal dob As Variant, _
                                     ByVal admission As Variant, ByVal folderName As Variant)
    Dim pid As Double
    pid = LaunchEdgeApp(BuildLetterUrl(caseEncounter, policyId, memberName, dob, admission, folderName))
    If pid > 0 Then WaitForProcess pid
End Sub

' Opens the letter form in a dialog-sized Edge window and returns immediately.
Public Sub OpenClinicalsLetter(ByVal caseEncounter As Variant, ByVal policyId As Variant, _
                               ByVal memberName As Variant, ByVal dob As Variant, _
                               ByVal admission As Variant, ByVal folderName As Variant)
    LaunchEdgeApp BuildLetterUrl(caseEncounter, policyId, memberName, dob, admission, folderName)
End Sub

' Builds the pre-filled URL (also useful for the Access-form approach below).
Public Function BuildLetterUrl(ByVal caseEncounter As Variant, ByVal policyId As Variant, _
                               ByVal memberName As Variant, ByVal dob As Variant, _
                               ByVal admission As Variant, ByVal folderName As Variant) As String
    BuildLetterUrl = LETTER_BASE_URL & "/letter/?case_encounter=" & UrlEnc(Nz(caseEncounter, "")) & _
                     "&policy_id=" & UrlEnc(Nz(policyId, "")) & _
                     "&member_name=" & UrlEnc(Nz(memberName, "")) & _
                     "&dob=" & UrlEnc(FormatDob(dob)) & _
                     "&admission=" & UrlEnc(Nz(admission, "")) & _
                     "&folder_name=" & UrlEnc(Nz(folderName, "")) & _
                     "&user=" & UrlEnc(Environ("USERNAME"))
End Function

' ===========================================================================
' Edge "app" window
' ===========================================================================

' Starts Edge in --app mode (no address bar or tabs) sized and centred like a
' dialog. A private profile folder keeps the window in its own process, which
' is what makes waiting for it possible. Returns the process id, or 0 if Edge
' was not found (the page is then opened in the default browser instead).
Private Function LaunchEdgeApp(ByVal url As String) As Double
    Dim edge As String, profile As String, cmd As String, x As Long, y As Long
    edge = FindEdge()
    If Len(edge) = 0 Then
        Application.FollowHyperlink url
        Exit Function
    End If
    profile = Environ("LOCALAPPDATA") & "\MapInc\LetterDialogProfile"
    x = (GetSystemMetrics(SM_CXSCREEN) - DIALOG_WIDTH) \ 2
    y = (GetSystemMetrics(SM_CYSCREEN) - DIALOG_HEIGHT) \ 2
    If x < 0 Then x = 0
    If y < 0 Then y = 0
    cmd = """" & edge & """ --app=""" & url & """" & _
          " --window-size=" & DIALOG_WIDTH & "," & DIALOG_HEIGHT & _
          " --window-position=" & x & "," & y & _
          " --user-data-dir=""" & profile & """ --no-first-run --no-default-browser-check"
    LaunchEdgeApp = Shell(cmd, vbNormalFocus)
End Function

Private Function FindEdge() As String
    Dim candidates As Variant, i As Integer
    candidates = Array("C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", _
                       "C:\Program Files\Microsoft\Edge\Application\msedge.exe")
    For i = LBound(candidates) To UBound(candidates)
        If Len(Dir(candidates(i))) > 0 Then
            FindEdge = candidates(i)
            Exit Function
        End If
    Next i
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

Private Function FormatDob(ByVal dob As Variant) As String
    If IsDate(dob) Then
        FormatDob = Format(dob, "yyyy-mm-dd")
    Else
        FormatDob = Nz(dob, "")
    End If
End Function

' Percent-encodes a string as UTF-8 for use in a query string.
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
    DoCmd.OpenForm "frmLetterDialog", acNormal, , , , acDialog, _
                   BuildLetterUrl(caseEncounter, policyId, memberName, dob, admission, folderName)
End Sub
