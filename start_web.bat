@echo off
setlocal

REM Change to repo root
cd /d "%~dp0"

REM Choose Python launcher (prefer py)
set "PY_CMD=python"
where py >nul 2>nul
if %errorlevel%==0 set "PY_CMD=py -3"

set "VENV_DIR=.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "RUN_PY=%PY_CMD%"

if not exist "%VENV_PY%" echo [tag2dir] Creating virtual environment... & %PY_CMD% -m venv "%VENV_DIR%"
if exist "%VENV_PY%" set "RUN_PY=%VENV_PY%"

REM Activate venv if available (optional)
if exist "%VENV_DIR%\Scripts\activate.bat" call "%VENV_DIR%\Scripts\activate.bat"

REM Install dependencies unless skipped
if not defined SKIP_INSTALL goto :INSTALL
goto :RUN

:INSTALL
if exist requirements.txt (
  echo [tag2dir] Installing dependencies (set SKIP_INSTALL=1 to skip)...
  %RUN_PY% -m pip install --upgrade pip
  %RUN_PY% -m pip install -r requirements.txt
)
if not exist requirements.txt echo [tag2dir] requirements.txt not found, skipping install.

:RUN
echo [tag2dir] Starting server at http://127.0.0.1:5000
%RUN_PY% -m app.server

endlocal
