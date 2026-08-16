@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
"%~dp0python\python.exe" "%~dp0launcher.py" %*
if errorlevel 1 pause
