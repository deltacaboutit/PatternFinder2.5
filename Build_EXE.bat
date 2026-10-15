@echo off
REM OPTIONAL. Turns the desktop app into one PatternFinder.exe file that runs
REM on any Windows PC, even one without Python.
cd /d "%~dp0"
title Build PatternFinder.exe
call windows\_setup.bat || exit /b 1
echo Installing the packaging tool (PyInstaller)...
".venv\Scripts\python.exe" -m pip install --upgrade pyinstaller || goto failed
echo Building PatternFinder.exe. This takes a few minutes...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name PatternFinder ^
    --collect-all yfinance --collect-all curl_cffi --collect-data certifi ^
    --hidden-import PIL._tkinter_finder ^
    --exclude-module streamlit --exclude-module plotly ^
    --add-data "pattern_core\images;pattern_core\images" ^
    desktop_app.py || goto failed
echo.
echo  Done! Your program is here:  %~dp0dist\PatternFinder.exe
pause
exit /b 0
:failed
echo  The build did not finish. Scroll up to see the error message.
pause
exit /b 1
