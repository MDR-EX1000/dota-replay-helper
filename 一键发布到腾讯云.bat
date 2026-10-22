@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ==========================================
echo  生成网页 - 上传到腾讯云 CloudBase
echo ==========================================
echo.
python deploy_tcb.py
echo.
pause
