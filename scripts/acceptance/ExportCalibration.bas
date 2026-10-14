Attribute VB_Name = "ExportCalibration"
Option Explicit

Private Function DecimalText(ByVal value As Single) As String
    DecimalText = Replace(Trim$(Str$(value)), ",", ".")
End Function

Public Sub ExportCalibration()
    Dim target As String, channel As Integer, opened As Boolean
    Dim slide As Slide, shape As Shape, text As Office.TextRange2
    target = InputBox("CSV output absolute path (new file)", "pptviper calibration")
    If Len(target) = 0 Then Exit Sub
    On Error GoTo Failed
    If Len(Dir$(target)) > 0 Then
        MsgBox "Output already exists. Choose a new path."
        Exit Sub
    End If
    channel = FreeFile
    Open target For Output As #channel
    opened = True
    Print #channel, "name,slide,shape_id,lines,width_pt,height_pt"
    For Each slide In ActivePresentation.Slides
        For Each shape In slide.Shapes
            If shape.Name Like "CAL-####" Then
                If shape.HasTextFrame = msoTrue Then
                    Set text = shape.TextFrame2.TextRange
                    Print #channel, shape.Name & "," & CStr(slide.SlideIndex) & "," & _
                        CStr(shape.Id) & "," & CStr(text.Lines.Count) & "," & _
                        DecimalText(text.BoundWidth) & "," & DecimalText(text.BoundHeight)
                End If
            End If
        Next shape
    Next slide
    Close #channel
    MsgBox "CSV exported. Record OS, PowerPoint version, operator and font substitutions."
    Exit Sub
Failed:
    If opened Then Close #channel
    MsgBox "Export failed: " & Err.Description & ". Discard the partial CSV."
End Sub
