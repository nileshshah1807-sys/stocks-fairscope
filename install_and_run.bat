@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.11+ from https://python.org and enable Add Python to PATH.
  pause
  exit /b 1
)
if not exist .venv (
  echo Creating private Python environment...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
echo Installing or updating required packages...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo Installation failed. Check your internet connection.
  pause
  exit /b 1
)
python app.py
if errorlevel 1 pause
