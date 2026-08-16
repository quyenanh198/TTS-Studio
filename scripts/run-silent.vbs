' Launch TTS Studio without a console window
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = root
sh.Environment("Process")("PYTHONUTF8") = "1"
sh.Run """" & root & "\python\pythonw.exe"" """ & root & "\launcher.py""", 0, False
