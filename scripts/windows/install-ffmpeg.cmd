@echo off
rem Download a portable, checksum-verified FFmpeg into tools\ffmpeg (no system changes).
rem The execution-policy flag applies to this one PowerShell process only.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-ffmpeg.ps1" %*
exit /b %errorlevel%
