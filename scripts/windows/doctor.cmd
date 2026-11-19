@echo off
rem Check that this computer has everything IDK Clips needs (read-only).
setlocal
cd /d "%~dp0..\..\backend"
if not exist ".venv\Scripts\python.exe" (
  echo IDK Clips is not set up yet. Run scripts\windows\setup.cmd first.
  exit /b 1
)
".venv\Scripts\python.exe" -m app doctor
