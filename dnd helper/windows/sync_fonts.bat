@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "DND_HELPER=%~dp0..\dnd_helper.py"

py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
    py -3 "%DND_HELPER%" sync_fonts %*
    goto finished
)
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
    python "%DND_HELPER%" sync_fonts %*
    goto finished
)
echo Install Python 3.10 or newer and make py or python available.
set "DND_RESULT=2"
goto wait_for_close

:finished
set "DND_RESULT=%ERRORLEVEL%"
:wait_for_close
echo.
pause
exit /b %DND_RESULT%
