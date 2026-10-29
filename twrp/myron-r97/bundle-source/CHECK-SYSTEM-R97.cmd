@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Capture-Battery-R96.ps1"
set "capture_result=%errorlevel%"
pause
endlocal & exit /b %capture_result%
