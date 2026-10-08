@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "SCRIPT_FOLDER=%~dp0"
powershell.exe -NoProfile -Command ^
    "$root = $env:SCRIPT_FOLDER;" ^
    "$files = @(Get-ChildItem -LiteralPath $root -Filter '*.mkv' -File | Sort-Object Name);" ^
    "if ($files.Count -eq 0) { Write-Host 'No MKV files found beside this BAT.'; exit 1 };" ^
    "$items = @(); $failures = 0;" ^
    "foreach ($file in $files) {" ^
    "  try {" ^
    "    $json = & mkvmerge -J $file.FullName;" ^
    "    if ($LASTEXITCODE -ne 0) { throw 'mkvmerge could not read this file' };" ^
    "    $info = ($json -join [Environment]::NewLine) | ConvertFrom-Json -ErrorAction Stop;" ^
    "    $items += [pscustomobject]@{ File = $file; Info = $info };" ^
    "  } catch { Write-Host ('ERROR reading ' + $file.Name + ': ' + $_.Exception.Message); $failures++ }" ^
    "};" ^
    "$options = @($items | ForEach-Object { $_.Info.tracks } | Where-Object { $_.type -eq 'subtitles' } | Group-Object -Property { ([string]$_.properties.track_name) + [char]31 + ([string]$_.properties.language) } | ForEach-Object { $_.Group[0] } | Sort-Object @{Expression={$_.properties.track_name}}, @{Expression={$_.properties.language}});" ^
    "if ($options.Count -eq 0) { Write-Host 'No subtitle tracks found.'; if ($failures) { exit 1 } else { exit 0 } };" ^
    "Write-Host ''; Write-Host 'Subtitle names and languages (across all MKVs):';" ^
    "for ($i = 0; $i -lt $options.Count; $i++) {" ^
    "  $name = [string]$options[$i].properties.track_name; $lang = [string]$options[$i].properties.language; $label = if ($name -eq '') { '(unnamed)' } else { $name }; if ($lang -eq '') { $lang = 'und' };" ^
    "  Write-Host ('  ' + ($i + 1) + '. [' + $lang + '] ' + $label);" ^
    "};" ^
    "Write-Host ''; $answer = Read-Host 'Enter numbers separated by commas or spaces (blank to cancel)';" ^
    "if ([string]::IsNullOrWhiteSpace($answer)) { Write-Host 'Cancelled.'; exit 0 };" ^
    "if ($answer -notmatch '^\s*[1-9][0-9]*(?:[\s,]+[1-9][0-9]*)*\s*$') { Write-Host 'Invalid selection.'; exit 1 };" ^
    "$numbers = @($answer.Trim() -split '[\s,]+' | ForEach-Object { [int]::Parse($_) } | Sort-Object -Unique);" ^
    "if (@($numbers | Where-Object { $_ -gt $options.Count }).Count) { Write-Host 'Number outside the list.'; exit 1 };" ^
    "$chosen = @($numbers | ForEach-Object { $t = $options[$_ - 1]; ([string]$t.properties.track_name) + [char]31 + ([string]$t.properties.language) });" ^
    "Write-Host ''; Write-Host 'Setting default flags for:';" ^
    "foreach ($number in $numbers) { $t = $options[$number - 1]; $label = if ([string]$t.properties.track_name -eq '') { '(unnamed)' } else { [string]$t.properties.track_name }; Write-Host ('  [' + $t.properties.language + '] ' + $label) };" ^
    "$answer = Read-Host 'Proceed? (Y/N)';" ^
    "if ($answer -notmatch '^(?i:y(?:es)?)$') { Write-Host 'Cancelled.'; exit 0 };" ^
    "$updated = 0;" ^
    "foreach ($item in $items) {" ^
    "  $matching = @($item.Info.tracks | Where-Object { $_.type -eq 'subtitles' -and $chosen -contains (([string]$_.properties.track_name) + [char]31 + ([string]$_.properties.language)) });" ^
    "  if ($matching.Count -eq 0) { continue };" ^
    "  $editArgs = @($item.File.FullName); $changed = 0;" ^
    "  try {" ^
    "    foreach ($track in $matching) {" ^
    "      if ($track.properties.default_track -eq $true) { continue };" ^
    "      if ($null -eq $track.properties.number) { throw ('Missing track number for track ID ' + $track.id) };" ^
    "      $editArgs += @('--edit', ('track:@' + $track.properties.number), '--set', 'flag-default=1');" ^
    "      $changed++;" ^
    "    };" ^
    "    if ($changed -eq 0) { Write-Host ('Already set: ' + $item.File.Name); continue };" ^
    "    Write-Host ('Editing ' + $item.File.Name + ': ' + $changed + ' track(s)');" ^
    "    & mkvpropedit @editArgs;" ^
    "    if ($LASTEXITCODE -ne 0) { throw ('mkvpropedit returned ' + $LASTEXITCODE) };" ^
    "    $json = & mkvmerge -J $item.File.FullName;" ^
    "    if ($LASTEXITCODE -ne 0) { throw 'Could not verify edited file' };" ^
    "    $after = ($json -join [Environment]::NewLine) | ConvertFrom-Json -ErrorAction Stop;" ^
    "    $missing = @($after.tracks | Where-Object { $_.type -eq 'subtitles' -and $chosen -contains (([string]$_.properties.track_name) + [char]31 + ([string]$_.properties.language)) -and $_.properties.default_track -ne $true });" ^
    "    if ($missing.Count) { throw ($missing.Count.ToString() + ' selected track(s) still lack the default flag') };" ^
    "    $updated++; Write-Host '  Verified.';" ^
    "  } catch { Write-Host ('ERROR editing ' + $item.File.Name + ': ' + $_.Exception.Message); $failures++ }" ^
    "};" ^
    "Write-Host ''; Write-Host ('Updated files: ' + $updated + '; failures: ' + $failures);" ^
    "if ($failures) { exit 1 } else { exit 0 }"
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
