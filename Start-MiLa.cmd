@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-MiLa.ps1" %*
set "launcher_exit=%ERRORLEVEL%"
echo.
if not "%launcher_exit%"=="0" echo Startup did not finish. Read the instructions above, fix the problem, and try again.
pause
exit /b %launcher_exit%
