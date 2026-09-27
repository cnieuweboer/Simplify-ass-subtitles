@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set "FIRST="

for %%F in (*.mkv) do (
    if not defined FIRST set "FIRST=%%~fF"
)

if not defined FIRST (
    echo No MKV files found in:
    echo %CD%
    echo.
    pause
    exit /b 1
)

echo.
echo Reading subtitle tracks from:
echo %FIRST%
echo.
echo Available subtitle tracks:
echo --------------------------

powershell -NoProfile -Command ^
    "$j = mkvmerge -J '%FIRST%' | ConvertFrom-Json;" ^
    "$subs = @($j.tracks | Where-Object { $_.type -eq 'subtitles' });" ^
    "for ($i=0; $i -lt $subs.Count; $i++) {" ^
    "  $t=$subs[$i];" ^
    "  $lang=$t.properties.language;" ^
    "  $name=$t.properties.track_name;" ^
    "  if (-not $lang) {$lang='und'};" ^
    "  if (-not $name) {$name='(no name)'};" ^
    "  Write-Host ('[{0}]  {1}  -  {2}' -f ($i+1),$lang,$name)" ^
    "}"

if errorlevel 1 (
    echo.
    echo ERROR: Could not read MKV tracks.
    pause
    exit /b 1
)

for /f %%N in ('powershell -NoProfile -Command "$j=mkvmerge -J '%FIRST%'|ConvertFrom-Json; @($j.tracks|Where-Object type -eq 'subtitles').Count"') do set "COUNT=%%N"

echo.
set /p "CHOICE=Enter subtitle number to make default: "

echo %CHOICE%| findstr /r "^[1-9][0-9]*$" >nul
if errorlevel 1 (
    echo.
    echo Invalid selection.
    pause
    exit /b 1
)

if %CHOICE% GTR %COUNT% (
    echo.
    echo Invalid selection. The first MKV has only %COUNT% subtitle tracks.
    pause
    exit /b 1
)

echo.
echo Setting subtitle track %CHOICE% as default...
echo.

for %%F in (*.mkv) do (
    echo Processing: %%~nxF

    mkvpropedit "%%~fF" --edit track:s%CHOICE% --set flag-default=1

    if errorlevel 1 (
        echo ERROR
    ) else (
        echo OK
    )

    echo.
)

echo Finished.
pause