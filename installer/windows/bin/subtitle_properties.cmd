@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "SUBTITLE_SCRIPT=%~dp0..\simplify-ass\subtitle_properties.py"
if not exist "%SUBTITLE_SCRIPT%" (
    echo Missing installed Python script: "%SUBTITLE_SCRIPT%"
    exit /b 2
)
set "SUBTITLE_PY=py -3"
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto launch
set "SUBTITLE_PY=python"
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto launch
echo Install Python 3.10 or newer and make py or python available.
exit /b 2

:launch
%SUBTITLE_PY% "%SUBTITLE_SCRIPT%" --input "%CD%\." %*
exit /b %ERRORLEVEL%
