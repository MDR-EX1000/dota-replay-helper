@echo off
chcp 65001 >nul
cd /d "%~dp0"
python stats.py
if errorlevel 1 pause & exit /b
python make_web.py
if errorlevel 1 pause & exit /b
start "" "docs\index.html"
