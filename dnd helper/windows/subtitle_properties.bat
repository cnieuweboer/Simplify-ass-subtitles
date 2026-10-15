@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "DND_SCRIPT=%~dp0subtitle_properties.py"
set "DND_RESULT=0"
if not exist "%DND_SCRIPT%" (
    echo Place this BAT beside subtitle_properties.py.
    set "DND_RESULT=2"
    goto finished
)
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
    set "DND_PY=py -3"
    goto launch
)
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
    set "DND_PY=python"
    goto launch
)
echo Install Python 3.10 or newer and make py or python available.
set "DND_RESULT=2"
goto finished

:launch
if "%~1"=="" (
    %DND_PY% "%DND_SCRIPT%" "%~dp0."
    if errorlevel 1 set "DND_RESULT=1"
    goto finished
)
:next_folder
if "%~1"=="" goto finished
if not exist "%~1" (
    echo Drop an MKV file or a folder containing MKVs: "%~1"
    set "DND_RESULT=2"
    goto finished
)
%DND_PY% "%DND_SCRIPT%" "%~1"
if errorlevel 1 set "DND_RESULT=1"
shift
goto next_folder

:finished
echo.
pause
exit /b %DND_RESULT%
