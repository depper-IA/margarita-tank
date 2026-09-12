@echo off
cd /d "%~dp0host"
echo Starting Clawd Tank daemon (BLE)...
".venv\Scripts\python.exe" -m clawd_tank_daemon.daemon
echo.
echo Daemon stopped (closed or crashed). Press any key to close this window.
pause >nul
