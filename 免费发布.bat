@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe deploy\publish_free.py
if errorlevel 1 echo Deployment did not complete. Please keep this window for troubleshooting.
pause
ms-0f2b8aa4-f99e-47f7-84a2-7d217bc74c58
