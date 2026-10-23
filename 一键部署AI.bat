@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ==========================================
echo  部署 AI 匹配助手（CloudBase 云函数）
echo ==========================================
echo.
python deploy_ai.py
echo.
pause
