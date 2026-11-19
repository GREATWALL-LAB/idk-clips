@echo off
rem =====================================================================
rem  IDK Clips - one-time setup for Windows
rem  Creates a Python virtual environment (backend\.venv) and installs the
rem  frontend packages (frontend\node_modules). Nothing is installed globally.
rem  Usage:  scripts\windows\setup.cmd          (run the app)
rem          scripts\windows\setup.cmd --dev    (also install test/lint tools)
rem =====================================================================
setlocal EnableExtensions
cd /d "%~dp0..\.."

set "REQS=backend\requirements.txt"
if /i "%~1"=="--dev" set "REQS=backend\requirements-dev.txt"

echo.
echo [IDK Clips] Checking prerequisites...
where python >nul 2>nul
if errorlevel 1 (
  echo   Python was not found. Install Python 3.11+ from https://www.python.org/downloads/
  echo   and tick "Add python.exe to PATH" during installation.
  exit /b 1
)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo   Python 3.11 or newer is required.
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo   Node.js was not found. Install the LTS version 20.9+ from https://nodejs.org/
  exit /b 1
)

if not exist "backend\.venv\Scripts\python.exe" (
  echo [IDK Clips] Creating Python virtual environment in backend\.venv ...
  python -m venv "backend\.venv"
  if errorlevel 1 exit /b 1
)

echo [IDK Clips] Installing backend packages from %REQS% ...
"backend\.venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check
if errorlevel 1 exit /b 1
"backend\.venv\Scripts\python.exe" -m pip install -r "%REQS%" --disable-pip-version-check
if errorlevel 1 exit /b 1
"backend\.venv\Scripts\python.exe" -m pip install -e processing --disable-pip-version-check
if errorlevel 1 exit /b 1

echo [IDK Clips] Installing frontend packages ...
pushd frontend
call npm ci --no-fund --no-audit
if errorlevel 1 (
  popd
  exit /b 1
)
echo [IDK Clips] Building the web interface (served by the backend in local mode) ...
call npm run build
if errorlevel 1 (
  popd
  exit /b 1
)
popd

echo.
if exist "tools\ffmpeg\bin\ffmpeg.exe" (
  echo [IDK Clips] FFmpeg: found in tools\ffmpeg
) else (
  where ffmpeg >nul 2>nul
  if errorlevel 1 (
    echo [IDK Clips] FFmpeg was not found. Run scripts\windows\install-ffmpeg.cmd
    echo               to download a portable copy into tools\ffmpeg.
  ) else (
    echo [IDK Clips] FFmpeg: found on PATH
  )
)
echo.
echo [IDK Clips] Checking the requirements ...
"backend\.venv\Scripts\python.exe" -m app doctor
echo [IDK Clips] Setup complete. Start the app with: scripts\windows\start.cmd
exit /b 0
