@echo off
setlocal EnableExtensions DisableDelayedExpansion

pushd "%~dp0" || (
    echo Could not open the BAT file's folder.
    pause
    exit /b 1
)

if not exist "*.mkv" (
    echo No MKV files found in this folder.
    popd
    pause
    exit /b 1
)

set /a FAILED=0
for %%F in (*.mkv) do (
    echo.
    echo Processing: %%~nxF
    set "MKV_FILE=%%~fF"

    powershell -NoProfile -Command ^
        "$file = $env:MKV_FILE;" ^
        "try {" ^
        "  $output = & mkvmerge -J $file;" ^
        "  if ($LASTEXITCODE -ne 0) { throw 'mkvmerge could not read the file' };" ^
        "  $info = ($output -join [Environment]::NewLine) | ConvertFrom-Json -ErrorAction Stop;" ^
        "  $subs = @($info.tracks | Where-Object { $_.type -eq 'subtitles' });" ^
        "  $editArgs = @($file);" ^
        "  for ($i = 0; $i -lt $subs.Count; $i++) {" ^
        "    if ($subs[$i].properties.default_track -eq $true) {" ^
        "      Write-Host ('  Clearing default flag: subtitle #' + ($i + 1));" ^
        "      $editArgs += '--edit';" ^
        "      $editArgs += ('track:s' + ($i + 1));" ^
        "      $editArgs += '--set';" ^
        "      $editArgs += 'flag-default=0';" ^
        "    }" ^
        "  }" ^
        "  if ($editArgs.Count -eq 1) { Write-Host '  No default subtitles found.'; exit 0 };" ^
        "  & mkvpropedit @editArgs;" ^
        "  if ($LASTEXITCODE -ne 0) { exit 1 };" ^
        "} catch { Write-Host ('  ERROR: ' + $_.Exception.Message); exit 1 }"

    if errorlevel 1 set /a FAILED+=1
)

echo.
if %FAILED% GTR 0 (
    echo Done with %FAILED% failed file(s).
) else (
    echo Done.
)
popd
pause
