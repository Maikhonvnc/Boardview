' Lancador do OpenBoardView via protocolo obvboard://
' O hub (navegador) abre  obvboard:///C:/caminho/placa.pcb  e isto lanca o OBV.
Set args = WScript.Arguments
If args.Count = 0 Then WScript.Quit
raw = args(0)
raw = Replace(raw, "obvboard:///", "")
raw = Replace(raw, "obvboard://", "")
raw = Replace(raw, "obvboard:", "")

' URL-decode (%20 etc.)
Dim i, c, res
res = ""
i = 1
Do While i <= Len(raw)
  c = Mid(raw, i, 1)
  If c = "%" And i + 2 <= Len(raw) Then
    res = res & Chr(CLng("&H" & Mid(raw, i + 1, 2)))
    i = i + 3
  Else
    res = res & c
    i = i + 1
  End If
Loop

res = Replace(res, "/", "\")
If Right(res, 1) = "\" Then res = Left(res, Len(res) - 1)

Dim exedir, exe
' pasta do OBV relativa a este .vbs (nao depende do usuario da maquina)
Set fso = CreateObject("Scripting.FileSystemObject")
exedir = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "OpenBoardView\openboardview-10.0.0-patched")
exe = exedir & "\openboardview.exe"

Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = exedir
sh.Run """" & exe & """ """ & res & """", 1, False
