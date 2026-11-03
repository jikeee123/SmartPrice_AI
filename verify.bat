@echo off
cd /d "%~dp0"
set PYTHONPATH=%CD%
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
if errorlevel 1 goto failed
.venv\Scripts\python.exe tests\check_ui.py
if errorlevel 1 goto failed
.venv\Scripts\python.exe tests\check_workflow_ui.py
if errorlevel 1 goto failed
echo Verification passed.
pause
exit /b 0
:failed
echo Verification failed.
pause
exit /b 1
