@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ==========================================
echo  同步网页上传的比赛到本地
echo ==========================================
echo.
python sync_cloud.py
echo.
pause
