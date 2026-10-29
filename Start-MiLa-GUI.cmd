@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher\Setup-MiLa.ps1" %*
exit /b %ERRORLEVEL%
