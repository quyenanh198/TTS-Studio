' Launch TTS Studio without a console window
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = root
sh.Environment("Process")("PYTHONUTF8") = "1"
' Show-state 1 (SW_SHOWNORMAL): pythonw has no console, and 0 (SW_HIDE) would be inherited by the app's
' first top-level window, leaving TTS Studio running invisibly.
sh.Run """" & root & "\python\pythonw.exe"" """ & root & "\launcher.py""", 1, False
