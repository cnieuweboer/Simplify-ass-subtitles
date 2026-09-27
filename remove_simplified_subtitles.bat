@echo off
setlocal

cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass ^
    -File "%~dp0remove_simplified_subtitles.ps1" ^
    -InputDirectory "%~dp0."

endlocal