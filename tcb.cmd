@echo off
setlocal
set "TOOLROOT=%~dp0.local-tools"
if not exist "%TOOLROOT%\node.exe" goto fallback
if not exist "%TOOLROOT%\cli\node_modules\.bin\tcb.cmd" goto fallback
set "PATH=%TOOLROOT%;%PATH%"
call "%TOOLROOT%\cli\node_modules\.bin\tcb.cmd" %*
exit /b %errorlevel%
:fallback
if not exist "%APPDATA%\npm\tcb.cmd" goto missing
call "%APPDATA%\npm\tcb.cmd" %*
exit /b %errorlevel%
:missing
echo CloudBase CLI not found. Install with: npm i -g @cloudbase/cli
exit /b 1
