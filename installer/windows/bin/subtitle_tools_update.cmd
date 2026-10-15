@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "UPDATE_SCRIPT=%~dp0..\simplify-ass\subtitle_tools_update.py"
if not exist "%UPDATE_SCRIPT%" (
    echo Missing installed updater: "%UPDATE_SCRIPT%"
    exit /b 2
)
set "UPDATE_PY=py -3"
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto launch
set "UPDATE_PY=python"
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto launch
echo Install Python 3.10 or newer and make py or python available.
exit /b 2

:launch
rem Parse this whole block before the updater replaces this CMD file.
(
    %UPDATE_PY% "%UPDATE_SCRIPT%" %*
    exit /b
)
