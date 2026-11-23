@echo off
setlocal
where cloudflared >nul 2>nul
if errorlevel 1 (
  echo Install cloudflared from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
  pause
  exit /b 1
)
echo Start the app first in another window using start_windows.bat.
echo This is a temporary test URL. It changes when restarted.
cloudflared tunnel --url http://localhost:8501
pause
