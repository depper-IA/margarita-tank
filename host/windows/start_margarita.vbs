' Starts the Margarita Tank tray app (daemon) with no console window.
' Uses the host venv next to this script: ..\.venv\Scripts\python.exe
Set fso = CreateObject("Scripting.FileSystemObject")
hostDir = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
python = hostDir & "\.venv\Scripts\python.exe"
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = hostDir
shell.Run """" & python & """ -m clawd_tank_menubar", 0, False
