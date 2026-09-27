@echo off
setlocal

set "SCRIPT=%~dp0simplify_ass.ps1"
set "INPUT=%~dp0."

echo Script: "%SCRIPT%"
echo Input:  "%INPUT%"
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -InputFolder "%INPUT%" -AddSimplifiedSubtitles 

echo.
echo Exit code: %ERRORLEVEL%
pause