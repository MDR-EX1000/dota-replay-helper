@echo off
setlocal
set "TOOLROOT=%~dp0.local-tools"
if not exist "%TOOLROOT%\node.exe" goto missing
if not exist "%TOOLROOT%\cli\node_modules\.bin\tcb.cmd" goto missing
set "PATH=%TOOLROOT%;%PATH%"
call "%TOOLROOT%\cli\node_modules\.bin\tcb.cmd" %*
exit /b %errorlevel%
:missing
echo Local CloudBase CLI is not ready. Run: python tools\setup_local_tools.py
exit /b 1
