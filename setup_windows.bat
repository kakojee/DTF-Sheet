@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Install Python 3.11+ from https://www.python.org/downloads/windows/ and select Add Python to PATH.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe py -3 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto fail
.venv\Scripts\pip.exe install -r requirements.txt
if errorlevel 1 goto fail
echo Setup complete. Run start_windows.bat to launch the app.
pause
exit /b 0
:fail
echo Setup failed. Read the error above and try again.
pause
exit /b 1
