@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run setup_windows.bat first.
  pause
  exit /b 1
)
echo On this PC: http://localhost:8501
echo To find the address for other devices, open another Command Prompt and run ipconfig.
echo Use the PC IPv4 address with port 8501, for example http://192.168.1.20:8501
.venv\Scripts\python.exe -m streamlit run app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true
