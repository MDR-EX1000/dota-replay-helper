@echo off
chcp 65001 >nul
cd /d "%~dp0"
python make_web.py
if errorlevel 1 pause & exit /b
start "" "C:\Users\admin\Desktop\replay\index.html"
