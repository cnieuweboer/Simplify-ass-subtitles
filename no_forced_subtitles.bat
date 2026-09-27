@echo off
setlocal

for %%F in (*.mkv) do (
    echo.
    echo Processing: %%F

    powershell -NoProfile -Command ^
        "$json = & mkvmerge -J '%%F' | ConvertFrom-Json; " ^
        "$subs = $json.tracks | Where-Object { $_.type -eq 'subtitles' }; " ^
        "foreach ($s in $subs) { " ^
        "  Write-Host ('  Clearing forced flag: track ID ' + $s.id); " ^
        "  & mkvpropedit '%%F' --edit ('track:@' + $s.id) --set flag-forced=0 " ^
        "}"
)

echo.
echo Done.
pause