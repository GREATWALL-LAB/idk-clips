@echo off
rem =====================================================================
rem  IDK Clips - start in local mode (no account, this computer only).
rem  One process serves the web interface and the API on http://localhost:8000
rem  For development with hot reload use scripts\windows\start-dev.cmd instead.
rem =====================================================================
setlocal
cd /d "%~dp0..\.."
if not exist "backend\.venv\Scripts\python.exe" (
  echo IDK Clips is not set up yet. Run scripts\windows\setup.cmd first.
  exit /b 1
)
if not exist "frontend\out\index.html" (
  echo The web interface has not been built yet. Run scripts\windows\setup.cmd again,
  echo or build it with:  cd frontend ^&^& npm run build
  exit /b 1
)
echo Opening http://localhost:8000 in a few seconds. Press Ctrl+C here to stop IDK Clips.
start "" /b cmd /c "timeout /t 4 /nobreak >nul & start "" http://localhost:8000/"
call "%~dp0start-backend.cmd"
