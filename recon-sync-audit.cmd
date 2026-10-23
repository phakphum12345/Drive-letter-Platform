@echo off
setlocal
set "ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%platform\recon-sync\recon-sync-engine.ps1" -Command audit -RepoRoot "%ROOT%" -Json
exit /b %ERRORLEVEL%
