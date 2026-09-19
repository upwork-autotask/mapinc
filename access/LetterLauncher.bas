Attribute VB_Name = "LetterLauncher"
Option Compare Database
Option Explicit

' ---------------------------------------------------------------------------
' Opens the MAP Inc "Clinicals Request" web form pre-filled for one case.
' Import this module into the Access database, set LETTER_BASE_URL, then call:
'   OpenClinicalsLetter Me.CaseEncounter, Me.PolicyID, Me.MemberName, Me.DOB, Me.Admission, Me.FolderName
' The folder name is the sub-folder under the PDF root configured in the web admin.
' ---------------------------------------------------------------------------

Private Const LETTER_BASE_URL As String = "http://SERVER-NAME:8000"   ' <-- change to the server running run.bat
Private Const EDGE_EXE As String = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

Public Sub OpenClinicalsLetter(ByVal caseEncounter As Variant, ByVal policyId As Variant, _
                               ByVal memberName As Variant, ByVal dob As Variant, _
                               ByVal admission As Variant, ByVal folderName As Variant)
    Dim url As String
    url = LETTER_BASE_URL & "/letter/?case_encounter=" & UrlEnc(Nz(caseEncounter, "")) & _
          "&policy_id=" & UrlEnc(Nz(policyId, "")) & _
          "&member_name=" & UrlEnc(Nz(memberName, "")) & _
          "&dob=" & UrlEnc(FormatDob(dob)) & _
          "&admission=" & UrlEnc(Nz(admission, "")) & _
          "&folder_name=" & UrlEnc(Nz(folderName, "")) & _
          "&user=" & UrlEnc(Environ("USERNAME"))
    OpenInAppWindow url
End Sub

Private Function FormatDob(ByVal dob As Variant) As String
    If IsDate(dob) Then
        FormatDob = Format(dob, "yyyy-mm-dd")
    Else
        FormatDob = Nz(dob, "")
    End If
End Function

Private Sub OpenInAppWindow(ByVal url As String)
    ' Edge "--app" mode opens a chromeless window that looks and behaves like a dialog.
    On Error GoTo Fallback
    If Dir(EDGE_EXE) = "" Then GoTo Fallback
    Shell """" & EDGE_EXE & """ --app=""" & url & """", vbNormalFocus
    Exit Sub
Fallback:
    On Error GoTo 0
    Application.FollowHyperlink url
End Sub

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
