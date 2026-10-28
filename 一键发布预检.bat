@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -B release_preflight.py
echo.
echo This check never logs in, uploads or publishes.
pause
