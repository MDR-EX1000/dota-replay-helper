@echo off
setlocal
set "TOOLROOT=%~dp0.local-tools"
if not exist "%TOOLROOT%\node.exe" goto fallback
if not exist "%TOOLROOT%\npm\bin\npm-cli.js" goto fallback
"%TOOLROOT%\node.exe" "%TOOLROOT%\npm\bin\npm-cli.js" %*
exit /b %errorlevel%
:fallback
if not exist "%ProgramFiles%\nodejs\npm.cmd" goto missing
call "%ProgramFiles%\nodejs\npm.cmd" %*
exit /b %errorlevel%
:missing
echo npm not found. Install Node.js with npm.
exit /b 1
