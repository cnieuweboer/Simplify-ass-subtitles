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
        "  foreach ($sub in $subs) {" ^
        "    if ($sub.properties.default_track -eq $true) {" ^
        "      if ($null -eq $sub.properties.number) { throw ('Missing track number for subtitle ID ' + $sub.id) };" ^
        "      Write-Host ('  Clearing default flag: track number ' + $sub.properties.number + ' - ' + $sub.properties.track_name);" ^
        "      $editArgs += '--edit';" ^
        "      $editArgs += ('track:@' + $sub.properties.number);" ^
        "      $editArgs += '--set';" ^
        "      $editArgs += 'flag-default=0';" ^
        "    }" ^
        "  }" ^
        "  if ($editArgs.Count -eq 1) { Write-Host '  No default subtitles found.'; exit 0 };" ^
        "  & mkvpropedit @editArgs;" ^
        "  if ($LASTEXITCODE -ne 0) { exit 1 };" ^
        "  $output = & mkvmerge -J $file;" ^
        "  if ($LASTEXITCODE -ne 0) { throw 'Could not verify the edited file' };" ^
        "  $after = ($output -join [Environment]::NewLine) | ConvertFrom-Json -ErrorAction Stop;" ^
        "  $remaining = @($after.tracks | Where-Object { $_.type -eq 'subtitles' -and $_.properties.default_track -eq $true });" ^
        "  if ($remaining.Count -gt 0) { throw ($remaining.Count.ToString() + ' default subtitle flag(s) remain') };" ^
        "  Write-Host '  Verified: no default subtitle flags remain.';" ^
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
