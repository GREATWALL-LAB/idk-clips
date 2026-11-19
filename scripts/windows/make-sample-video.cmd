@echo off
rem Create data\samples\curious-minds-sample.mp4 (original script + Windows text-to-speech).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make-sample-video.ps1" %*
exit /b %errorlevel%
