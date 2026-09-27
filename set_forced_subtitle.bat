@echo off
setlocal EnableExtensions DisableDelayedExpansion

pushd "%~dp0" || (
    echo Could not open the BAT file's folder.
    pause
    exit /b 1
)

powershell -NoProfile -Command ^
    "$files = @(Get-ChildItem -LiteralPath . -Filter '*.mkv' -File | Sort-Object Name);" ^
    "if ($files.Count -eq 0) { Write-Host 'No MKV files found in this folder.'; exit 1 };" ^
    "Write-Host ('Reading subtitles from: ' + $files[0].Name);" ^
    "try {" ^
    "  $output = & mkvmerge -J ($files[0].FullName);" ^
    "  if ($LASTEXITCODE -ne 0) { throw 'mkvmerge could not read the first file' };" ^
    "  $info = ($output -join [Environment]::NewLine) | ConvertFrom-Json -ErrorAction Stop;" ^
    "} catch { Write-Host ('ERROR: ' + $_.Exception.Message); exit 1 };" ^
    "$subs = @($info.tracks | Where-Object { $_.type -eq 'subtitles' });" ^
    "if ($subs.Count -eq 0) { Write-Host 'No subtitle tracks found.'; exit 1 };" ^
    "Write-Host ''; Write-Host 'Available subtitle tracks:';" ^
    "for ($i = 0; $i -lt $subs.Count; $i++) {" ^
    "  $lang = $subs[$i].properties.language; if (-not $lang) { $lang = 'und' };" ^
    "  $name = $subs[$i].properties.track_name; if (-not $name) { $name = '(no name)' };" ^
    "  Write-Host ('[{0}]  {1}  -  {2}' -f ($i + 1), $lang, $name);" ^
    "};" ^
    "Write-Host ''; $inputNumber = Read-Host 'Enter subtitle number to mark as forced';" ^
    "$choice = 0;" ^
    "if (($inputNumber -notmatch '^[1-9][0-9]*$') -or (-not [int]::TryParse($inputNumber, [ref]$choice)) -or ($choice -gt $subs.Count)) { Write-Host 'Invalid selection.'; exit 1 };" ^
    "Write-Host ''; $failed = 0;" ^
    "foreach ($file in $files) {" ^
    "  Write-Host ('Processing: ' + $file.Name);" ^
    "  & mkvpropedit ($file.FullName) --edit ('track:s' + $choice) --set flag-forced=1;" ^
    "  if ($LASTEXITCODE -ne 0) { Write-Host '  ERROR'; $failed++ } else { Write-Host '  OK' };" ^
    "};" ^
    "Write-Host ''; Write-Host ('Done. Failed files: ' + $failed);" ^
    "if ($failed -gt 0) { exit 1 }"

popd
echo.
pause
