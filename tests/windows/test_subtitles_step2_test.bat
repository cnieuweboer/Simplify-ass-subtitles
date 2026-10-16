@echo off
setlocal
echo Subtitle simplifier launcher v181
rem Edit these settings before running.
set "CACHE_FOLDER=%~dp0cache"
set "OUTPUT_FOLDER=%~dp0results"
rem Leave blank for automatic local/repository/PATH lookup; or set an explicit Python script.
set "SIMPLIFIER="
rem Use python or the full path to python.exe.
set "PYTHON=python"
set "MAX_PARALLEL=16"

rem Optional overrides: leave blank to use simplify_ass.py's own defaults.
rem Scrolling concurrency: engine default 32; 0 disables dropping.
set "SCROLL_CONCURRENCY_LIMIT="
rem Minimum caption color hold in seconds: engine default 1; 0 disables this limit.
set "COLOR_PHASE_MIN_HOLD="
rem Seconds per caption color change: engine default 0 (unlimited).
set "COLOR_PHASE_CHANGE_INTERVAL="

set "SCROLL_OPTION="
if defined SCROLL_CONCURRENCY_LIMIT set "SCROLL_OPTION=-ScrollConcurrencyLimit %SCROLL_CONCURRENCY_LIMIT%"
set "COLOR_HOLD_OPTION="
if defined COLOR_PHASE_MIN_HOLD set "COLOR_HOLD_OPTION=-ColorPhaseMinHold %COLOR_PHASE_MIN_HOLD%"
set "COLOR_INTERVAL_OPTION="
if defined COLOR_PHASE_CHANGE_INTERVAL set "COLOR_INTERVAL_OPTION=-ColorPhaseChangeInterval %COLOR_PHASE_CHANGE_INTERVAL%"

if not exist "%~dp0test_subtitles_step2_test.ps1" (
    echo Missing test_subtitles_step2_test.ps1 beside this BAT file.
    pause
    exit /b 1
)
set "SIMPLIFIER_OPTION="
if defined SIMPLIFIER set "SIMPLIFIER_OPTION=-Simplifier "%SIMPLIFIER%""
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_subtitles_step2_test.ps1" -InputFolder "%CACHE_FOLDER%" -OutputFolder "%OUTPUT_FOLDER%" %SIMPLIFIER_OPTION% -Python "%PYTHON%" -MaxParallel %MAX_PARALLEL% -SimplificationLevel 1 %SCROLL_OPTION% %COLOR_HOLD_OPTION% %COLOR_INTERVAL_OPTION%
set "RUN_EXIT=%ERRORLEVEL%"
echo.
if "%RUN_EXIT%"=="0" (echo Tests finished.) else (echo Tests reported errors. Exit code: %RUN_EXIT%)
pause
exit /b %RUN_EXIT%
