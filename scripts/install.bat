@echo off
cd /d "%~dp0.."
echo Installiere Denon HEOS Controller...
py -m venv .venv
if errorlevel 1 (
  echo Python Launcher nicht verfuegbar, versuche python direkt...
  python -m venv .venv
)
if not exist .venv\Scripts\activate.bat (
  echo Virtuelle Umgebung konnte nicht erstellt werden.
  echo Bitte pruefen, ob Python installiert und im PATH ist.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo Fertig. Starte danach: scripts\start_web.bat
pause
