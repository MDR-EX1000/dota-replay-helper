@echo off
setlocal
set "TOOLROOT=%~dp0.local-tools"
if not exist "%TOOLROOT%\npm\bin\npm-cli.js" goto missing
"%TOOLROOT%\node.exe" "%TOOLROOT%\npm\bin\npm-cli.js" %*
exit /b %errorlevel%
:missing
echo Local npm is not ready. Run: python tools\setup_local_tools.py
exit /b 1
