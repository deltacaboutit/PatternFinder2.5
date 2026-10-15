@echo off
REM Double-click to open the Windows desktop app.
cd /d "%~dp0"
call windows\_setup.bat || exit /b 1
start "" ".venv\Scripts\pythonw.exe" desktop_app.py
