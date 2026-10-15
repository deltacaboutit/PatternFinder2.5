@echo off
REM Runs the phone/web version on this PC. A browser tab opens.
REM Your iPhone can use it too on the same Wi-Fi: type the "Network URL" shown below into Safari.
REM Keep this window open while you use it. Close it to stop.
cd /d "%~dp0"
title Pattern Finder (web version)
call windows\_setup.bat || exit /b 1
".venv\Scripts\python.exe" -m streamlit run streamlit_app.py
pause
