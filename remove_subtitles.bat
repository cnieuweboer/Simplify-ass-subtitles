@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "SUBTITLE_SCRIPT_FOLDER=%~dp0"
powershell.exe -NoProfile -Command ^
    "$ErrorActionPreference = 'Stop';" ^
    "$root = $env:SUBTITLE_SCRIPT_FOLDER;" ^
    "if (-not (Get-Command mkvmerge -ErrorAction SilentlyContinue)) { Write-Host 'ERROR: mkvmerge.exe was not found in PATH.'; exit 1 };" ^
    "$files = @(Get-ChildItem -LiteralPath $root -Filter '*.mkv' -File | Sort-Object Name);" ^
    "if ($files.Count -eq 0) { Write-Host 'No MKV files found beside this script.'; exit 0 };" ^
    "$items = @(); $scanFailed = 0;" ^
    "Write-Host 'Scanning MKV files...';" ^
    "foreach ($file in $files) {" ^
    "    try {" ^
    "        $raw = & mkvmerge -J $file.FullName;" ^
    "        if ($LASTEXITCODE -ne 0) { throw ('mkvmerge returned ' + $LASTEXITCODE) };" ^
    "        $info = ($raw -join [Environment]::NewLine) | ConvertFrom-Json -ErrorAction Stop;" ^
    "        $items += [pscustomobject]@{ File = $file; Info = $info };" ^
    "    } catch { Write-Host ('ERROR reading ' + $file.Name + ': ' + $_.Exception.Message); $scanFailed++ };" ^
    "};" ^
    "$options = @($items | ForEach-Object { $_.Info.tracks } | Where-Object { $_.type -eq 'subtitles' } | Group-Object -Property { ([string]$_.properties.track_name) + [char]31 + ([string]$_.properties.language) } | ForEach-Object { $_.Group[0] } | Sort-Object @{Expression={$_.properties.track_name}}, @{Expression={$_.properties.language}});" ^
    "if ($options.Count -eq 0) { Write-Host 'No subtitle tracks found.'; if ($scanFailed) { exit 1 } else { exit 0 } };" ^
    "Write-Host ''; Write-Host 'Subtitle tracks found (name and language):';" ^
    "for ($i = 0; $i -lt $options.Count; $i++) {" ^
    "    $track = $options[$i]; $name = [string]$track.properties.track_name; $lang = [string]$track.properties.language;" ^
    "    if ($name -eq '') { $name = '(unnamed)' }; if ($lang -eq '') { $lang = 'und' };" ^
    "    Write-Host ('  ' + ($i + 1) + '. [' + $lang + '] ' + $name);" ^
    "};" ^
    "Write-Host ''; $answer = Read-Host 'Enter numbers separated by commas or spaces (blank to cancel)';" ^
    "if ([string]::IsNullOrWhiteSpace($answer)) { Write-Host 'Cancelled.'; exit 0 };" ^
    "if ($answer -notmatch '^\s*[1-9][0-9]*(?:[\s,]+[1-9][0-9]*)*\s*$') { Write-Host 'Invalid selection.'; exit 1 };" ^
    "$numbers = @($answer.Trim() -split '[\s,]+' | ForEach-Object { [int]::Parse($_) } | Sort-Object -Unique);" ^
    "if (@($numbers | Where-Object { $_ -gt $options.Count }).Count) { Write-Host 'Number outside the list.'; exit 1 };" ^
    "$chosen = @($numbers | ForEach-Object { $track = $options[$_ - 1]; ([string]$track.properties.track_name) + [char]31 + ([string]$track.properties.language) });" ^
    "Write-Host ''; Write-Host 'Selected subtitles:';" ^
    "foreach ($number in $numbers) {" ^
    "    $track = $options[$number - 1]; $name = [string]$track.properties.track_name; $lang = [string]$track.properties.language;" ^
    "    if ($name -eq '') { $name = '(unnamed)' }; if ($lang -eq '') { $lang = 'und' };" ^
    "    Write-Host ('  [' + $lang + '] ' + $name);" ^
    "};" ^
    "$answer = Read-Host 'Remove these subtitles from matching MKVs? (Y/N)';" ^
    "if ($answer -notmatch '^(?i:y(?:es)?)$') { Write-Host 'Cancelled.'; exit 0 };" ^
    "$outputDir = Join-Path $root 'output';" ^
    "if (-not (Test-Path -LiteralPath $outputDir)) { New-Item -ItemType Directory -Path $outputDir | Out-Null };" ^
    "$changed = 0; $notFound = 0; $failed = $scanFailed; $existing = 0;" ^
    "foreach ($item in $items) {" ^
    "    $file = $item.File; $target = Join-Path $outputDir $file.Name;" ^
    "    $matching = @($item.Info.tracks | Where-Object { $_.type -eq 'subtitles' -and $chosen -contains (([string]$_.properties.track_name) + [char]31 + ([string]$_.properties.language)) });" ^
    "    if ($matching.Count -eq 0) { $notFound++; continue };" ^
    "    if (Test-Path -LiteralPath $target) { Write-Host ('Skipping existing output: ' + $file.Name); $existing++; continue };" ^
    "    $ids = @($matching | ForEach-Object { $_.id });" ^
    "    Write-Host ('Removing ' + $matching.Count + ' subtitle track(s) from ' + $file.Name);" ^
    "    try {" ^
    "        & mkvmerge -o $target --subtitle-tracks ('!' + ($ids -join ',')) $file.FullName;" ^
    "        if ($LASTEXITCODE -ne 0) { throw ('mkvmerge returned ' + $LASTEXITCODE) };" ^
    "        $raw = & mkvmerge -J $target;" ^
    "        if ($LASTEXITCODE -ne 0) { throw 'Could not verify output' };" ^
    "        $result = ($raw -join [Environment]::NewLine) | ConvertFrom-Json -ErrorAction Stop;" ^
    "        $remaining = @($result.tracks | Where-Object { $_.type -eq 'subtitles' -and $chosen -contains (([string]$_.properties.track_name) + [char]31 + ([string]$_.properties.language)) });" ^
    "        $beforeCount = @($item.Info.tracks | Where-Object { $_.type -eq 'subtitles' }).Count;" ^
    "        $afterCount = @($result.tracks | Where-Object { $_.type -eq 'subtitles' }).Count;" ^
    "        if ($remaining.Count -gt 0 -or $afterCount -ne ($beforeCount - $matching.Count)) { throw 'Output subtitle tracks did not match the selection' };" ^
    "        $changed++; Write-Host '  Verified.';" ^
    "    } catch {" ^
    "        Write-Host ('  ERROR: ' + $_.Exception.Message); $failed++;" ^
    "        if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force };" ^
    "    };" ^
    "};" ^
    "Write-Host ''; Write-Host ('Files changed: ' + $changed + '; no matches: ' + $notFound + '; existing outputs: ' + $existing + '; failed: ' + $failed);" ^
    "Write-Host ('Output folder: ' + $outputDir);" ^
    "if ($failed) { exit 1 } else { exit 0 };"
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
