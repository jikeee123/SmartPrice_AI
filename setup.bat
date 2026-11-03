@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.10 -m venv .venv
  if errorlevel 1 python -m venv .venv
)
if not exist .venv\Scripts\python.exe goto failed
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe prepare.py
if errorlevel 1 goto failed
echo Setup complete. Double-click run_app.bat to launch.
pause
exit /b 0
:failed
echo Setup failed. Check Python 3.10 and network connectivity.
pause
exit /b 1
