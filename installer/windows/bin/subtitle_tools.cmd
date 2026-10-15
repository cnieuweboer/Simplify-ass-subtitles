@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "MENU_SCRIPT=%~dp0..\simplify-ass\subtitle_tools.py"
if not exist "%MENU_SCRIPT%" (
    echo Missing installed menu: "%MENU_SCRIPT%"
    exit /b 2
)
set "MENU_PY=py -3"
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto launch
set "MENU_PY=python"
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto launch
echo Install Python 3.10 or newer and make py or python available.
exit /b 2

:launch
rem Parse this whole block before the updater replaces this CMD file.
(
    %MENU_PY% "%MENU_SCRIPT%" %*
    exit /b
)
