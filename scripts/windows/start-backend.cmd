@echo off
rem Start the IDK Clips backend API (FastAPI) on the host/port from .env (default 127.0.0.1:8000).
rem Pass --reload to restart automatically when backend code changes.
setlocal
cd /d "%~dp0..\..\backend"
if not exist ".venv\Scripts\python.exe" (
  echo Backend is not set up yet. Run scripts\windows\setup.cmd first.
  exit /b 1
)
".venv\Scripts\python.exe" -m app %*
