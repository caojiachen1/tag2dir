@echo off
REM Minimal launcher using system Python only. No venv, no installs.
cd /d "%~dp0"

REM Prefer py launcher if available
set "PY_CMD=python"
where py >nul 2>nul
if %errorlevel%==0 set "PY_CMD=py -3"

echo [tag2dir] Starting server at http://127.0.0.1:5000
%PY_CMD% -m app.server
