@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run setup_windows.bat first.
  pause
  exit /b 1
)
start "kakojee Print Nest" http://localhost:8501
.venv\Scripts\python.exe -m streamlit run app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true
