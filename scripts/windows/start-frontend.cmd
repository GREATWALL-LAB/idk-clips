@echo off
rem Start the IDK Clips web interface (Next.js dev server) on http://localhost:3000.
setlocal
cd /d "%~dp0..\..\frontend"
if not exist "node_modules" (
  echo Frontend is not set up yet. Run scripts\windows\setup.cmd first.
  exit /b 1
)
call npm run dev
