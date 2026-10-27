@echo off
chcp 65001 >nul
cd /d "%~dp0"
python sync_cloud.py --quiet
python stats.py
echo.
pause
