@echo off
rem Development: backend with auto-reload and the Next.js dev server, in two windows.
setlocal
start "IDK Clips - backend" cmd /k ""%~dp0start-backend.cmd" --reload"
start "IDK Clips - frontend" cmd /k ""%~dp0start-frontend.cmd""
echo.
echo   IDK Clips (development) is starting in two new windows.
echo   App:      http://localhost:3000
echo   API docs: http://localhost:8000/api/docs
echo   Close both windows (or press Ctrl+C in them) to stop.
echo.
