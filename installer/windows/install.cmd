@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "INSTALL_PY=py -3"
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto install
set "INSTALL_PY=python"
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto install
echo Install Python 3.10 or newer and make py or python available.
set "INSTALL_EXIT=2"
goto finished

:install
%INSTALL_PY% "%~dp0install.py" %*
set "INSTALL_EXIT=%ERRORLEVEL%"

:finished
if "%~1"=="" pause
exit /b %INSTALL_EXIT%
