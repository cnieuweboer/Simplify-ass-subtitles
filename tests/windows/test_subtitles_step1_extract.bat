@echo off
setlocal
rem Edit these folders before running.
set "INPUT_FOLDER=Z:\Documents\Video\anime"
set "CACHE_FOLDER=%~dp0\cache"
rem Leave blank to detect MKVToolNix automatically.
set "MKVTOOLNIX_FOLDER="

if not exist "%~dp0test_subtitles_step1_extract.ps1" (
    echo Missing extract_mkv_test_data.ps1 beside this BAT file.
    pause
    exit /b 1
)
if defined MKVTOOLNIX_FOLDER (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_subtitles_step1_extract.ps1" -InputFolder "%INPUT_FOLDER%" -OutputFolder "%CACHE_FOLDER%" -MkvToolNixFolder "%MKVTOOLNIX_FOLDER%"
) else (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_subtitles_step1_extract.ps1" -InputFolder "%INPUT_FOLDER%" -OutputFolder "%CACHE_FOLDER%"
)
set "RUN_EXIT=%ERRORLEVEL%"
echo.
if "%RUN_EXIT%"=="0" (echo Extraction finished.) else (echo Extraction failed. Exit code: %RUN_EXIT%)
pause
exit /b %RUN_EXIT%
