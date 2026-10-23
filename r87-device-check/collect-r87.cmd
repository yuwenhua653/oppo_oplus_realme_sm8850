@echo off
setlocal
cd /d "%~dp0"
set "R87_ADB=adb"
if exist "%~dp0..\adb.exe" set "R87_ADB=%~dp0..\adb.exe"
if exist "%~dp0adb.exe" set "R87_ADB=%~dp0adb.exe"
"%R87_ADB%" get-state >nul 2>&1
if errorlevel 1 (
  echo ADB device is not ready. Enable USB debugging and accept the phone prompt.
  echo Put this folder beside adb.exe, or add platform-tools to PATH.
  exit /b 1
)
echo Collecting read-only R87 diagnostics. No root is required.
"%R87_ADB%" shell sh -s < "%~dp0collect-r87.sh" > "%~dp0r87-check.txt" 2>&1
if errorlevel 1 (
  echo ADB capture failed. Details are in r87-check.txt.
  exit /b 1
)
findstr /C:"R87_RUNTIME_CAPTURE_END" "%~dp0r87-check.txt" >nul
if errorlevel 1 (
  echo Capture ended early. Send r87-check.txt for inspection.
  exit /b 1
)
echo Complete. Send r87-check.txt and your charger/meter observations.
echo Missing or unreadable optional paths are recorded and do not stop capture.
exit /b 0
