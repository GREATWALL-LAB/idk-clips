@echo off
rem =====================================================================
rem  IDK Clips worker: processes your videos on this computer for your
rem  online account (hybrid mode). Examples:
rem    scripts\windows\worker.cmd pair --server https://api.example.com --code ABCD-EFGH
rem    scripts\windows\worker.cmd run
rem    scripts\windows\worker.cmd status ^| unpair ^| doctor ^| purge --yes
rem =====================================================================
setlocal
cd /d "%~dp0..\..\backend"
if not exist ".venv\Scripts\python.exe" (
  echo IDK Clips is not set up yet. Run scripts\windows\setup.cmd first.
  exit /b 1
)
".venv\Scripts\python.exe" -m app.agent %*
