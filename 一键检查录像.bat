@echo off
chcp 65001 >nul
cd /d "%~dp0"
python check_dem.py
echo.
pause
