@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PATH=%~dp0.local-tools;%PATH%"
python -B release_preflight.py --local-only
if errorlevel 1 goto failed
python -B -m unittest discover -s tests
if errorlevel 1 goto failed
node.exe --test tests/player_profiles.test.cjs
if errorlevel 1 goto failed
node.exe --check upload_service/server.js
if errorlevel 1 goto failed
python -B make_web.py --matches-dir json/feature_validation --output-dir cloudrun_test/preview --local-preview --no-avatar-refresh
if errorlevel 1 goto failed
echo.
echo Local validation passed. No cloud login, upload or deployment was performed.
if not "%~1"=="--no-pause" pause
exit /b 0
:failed
echo.
echo Local validation did not pass. See the output above. Nothing was published.
if not "%~1"=="--no-pause" pause
exit /b 1
