@echo off
setlocal
set "ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%platform\recon-sync\recon-sync-engine.ps1" -Command status -RepoRoot "%ROOT%"
set "RC=%ERRORLEVEL%"
echo.
echo Recon-Sync status exit code: %RC%
pause
exit /b %RC%
