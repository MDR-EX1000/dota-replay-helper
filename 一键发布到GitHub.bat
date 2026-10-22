@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ==========================================
echo  生成网页 - 提交 - 推送 - 更新 GitHub Pages
echo ==========================================
echo.
python deploy.py
echo.
pause
