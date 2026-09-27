@echo off
setlocal

set "SCRIPT=%~dp0simplify_ass.ps1"
set "INPUT=%~dp0."

if not exist "%SCRIPT%" (
    echo Cannot find simplify_ass.ps1 beside this batch file.
    echo Place PowerShell and Python scripts in the same folder.
    pause
    exit /b 1
)

echo Input folder: "%INPUT%"
echo.
echo What should happen to the original subtitle tracks?
echo   1. Replace originals with simplified subtitles
echo   2. Keep originals and add simplified subtitles
choice /C 12 /N /M "Press 1 or 2: "
if errorlevel 3 goto :cancelled
if not errorlevel 1 goto :cancelled
if errorlevel 2 (set "ADD=-AddSimplifiedSubtitles") else (set "ADD=")

echo.
echo Which simplification level?
echo   1. Aggressive: simplify effects and remove vector drawings
echo   2. Visual: keep static text formatting and manageable vector drawings
choice /C 12 /N /M "Press 1 or 2: "
if errorlevel 3 goto :cancelled
if not errorlevel 1 goto :cancelled
if errorlevel 2 (set "LEVEL=2") else (set "LEVEL=1")

echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -InputFolder "%INPUT%" -SimplificationLevel %LEVEL% %ADD%
set "RESULT=%ERRORLEVEL%"
echo.
echo Exit code: %RESULT%
pause
exit /b %RESULT%

:cancelled
echo Cancelled.
pause
exit /b 1
