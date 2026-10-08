@echo off
setlocal
echo Subtitle simplifier launcher v102

set "SCRIPT=%~dp0simplify_ass.ps1"
set "INPUT=%~dp0."

rem Optional scrolling-text limit: leave blank to use the wrapper default.
rem Set 32 or another ceiling; 0 disables dropping. Requires simplify_ass.py version 101 or newer.
set "SCROLL_CONCURRENCY_LIMIT="
set "SCROLL_OPTION="
if defined SCROLL_CONCURRENCY_LIMIT set "SCROLL_OPTION=-ScrollConcurrencyLimit %SCROLL_CONCURRENCY_LIMIT%"

if not exist "%SCRIPT%" (
    echo Cannot find simplify_ass.ps1 beside this batch file.
    echo Place PowerShell and Python scripts in the same folder.
    pause
    exit /b 1
)

echo Input folder: "%INPUT%"
echo.
echo What should happen to the original subtitle tracks?
echo   1. Keep originals and add simplified subtitles
echo   2. Replace originals with simplified subtitles
choice /C 12 /N /M "Press 1 or 2: "
if errorlevel 3 goto :cancelled
if not errorlevel 1 goto :cancelled
if errorlevel 2 (set "MODE=-ReplaceOriginals") else (set "MODE=-AddSimplifiedSubtitles")

echo.
echo Which subtitle tracks should be added or replaced?
echo   1. Only tracks above 50 kB with more than 10%% fewer events
echo   2. All ASS/SSA tracks
choice /C 12 /N /M "Press 1 or 2: "
if errorlevel 3 goto :cancelled
if not errorlevel 1 goto :cancelled
if errorlevel 2 (set "FILTER=-ProcessAllTracks") else (set "FILTER=")

echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -InputFolder "%INPUT%" -SimplificationLevel 1 %MODE% %FILTER% %SCROLL_OPTION%
set "RESULT=%ERRORLEVEL%"
echo.
echo Exit code: %RESULT%
pause
exit /b %RESULT%

:cancelled
echo Cancelled.
pause
exit /b 1
