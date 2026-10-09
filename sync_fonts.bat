@echo off
setlocal

REM Set to 1 to write font reports, or 0 for MKV files only.
set "SAVE_LOGS=0"

cd /d "%~dp0"
set "LOG_OPTION="
if "%SAVE_LOGS%"=="1" set "LOG_OPTION=--log"

python -c "import sys" >nul 2>nul
if not errorlevel 1 (
    python "%~dp0sync_fonts.py" "%~dp0." %LOG_OPTION% %*
) else (
    py -3 "%~dp0sync_fonts.py" "%~dp0." %LOG_OPTION% %*
)
set "sync_result=%errorlevel%"
echo.
pause
exit /b %sync_result%
