@echo off
cd /d "%~dp0.."
if not exist .venv\Scripts\activate.bat (
  echo Virtuelle Umgebung fehlt. Bitte zuerst scripts\install.bat starten.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python run.py
pause
