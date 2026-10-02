@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0START.ps1" -Mode local %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo Startup failed with exit code %RC%.
  pause
)
exit /b %RC%
