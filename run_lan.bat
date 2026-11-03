@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Please run setup.bat first.
  pause
  exit /b 1
)
echo SmartPrice AI LAN server - port 8502
echo Share http://YOUR_LAN_IP:8502 with people on the same network.
echo Keep this window and computer running. Press Ctrl+C to stop.
ipconfig | findstr /i "IPv4"
.venv\Scripts\python.exe -m streamlit run app.py --server.address 0.0.0.0 --server.port 8502 --server.headless true --browser.gatherUsageStats false
pause
