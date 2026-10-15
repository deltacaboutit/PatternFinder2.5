@echo off
REM Runs every self-test of the shared engine. Use it after any change.
cd /d "%~dp0"
call windows\_setup.bat || exit /b 1
".venv\Scripts\python.exe" run_tests.py
pause
