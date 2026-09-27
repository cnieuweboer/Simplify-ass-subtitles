param (
    [string]$InputDirectory = "."
)

$ErrorActionPreference = "Stop"

# Find MKVToolNix
$mkvmerge = Get-Command "mkvmerge.exe" -ErrorAction SilentlyContinue

if (-not $mkvmerge) {
    $possiblePaths = @(
        "C:\Program Files\MKVToolNix\mkvmerge.exe",
        "C:\Program Files (x86)\MKVToolNix\mkvmerge.exe"
    )

    foreach ($path in $possiblePaths) {
        if (Test-Path $path) {
            $mkvmerge = $path
            break
        }
    }
}

if (-not $mkvmerge) {
    Write-Host "ERROR: mkvmerge.exe could not be found." -ForegroundColor Red
    pause
    exit 1
}

if ($mkvmerge -isnot [string]) {
    $mkvmerge = $mkvmerge.Source
}

# Create output folder
$outputDirectory = Join-Path $InputDirectory "output"

if (-not (Test-Path $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory | Out-Null
}

$files = Get-ChildItem -LiteralPath $InputDirectory -Filter "*.mkv" -File

if (-not $files) {
    Write-Host "No MKV files found."
    pause
    exit
}

foreach ($file in $files) {

    Write-Host ""
    Write-Host "Checking: $($file.Name)" -ForegroundColor Cyan

    $json = & $mkvmerge -J $file.FullName | ConvertFrom-Json

    $subtitleTracks = @(
        $json.tracks | Where-Object {
            $_.type -eq "subtitles"
        }
    )

    if ($subtitleTracks.Count -eq 0) {
        Write-Host "  No subtitle tracks found. Skipping." -ForegroundColor DarkGray
        continue
    }

    # Collect all existing subtitle names
    $subtitleNames = @(
        $subtitleTracks |
        ForEach-Object {
            $_.properties.track_name
        } |
        Where-Object {
            -not [string]::IsNullOrWhiteSpace($_)
        }
    )

    $removeTrackIds = @()

    foreach ($track in $subtitleTracks) {

        $name = $track.properties.track_name

        if ([string]::IsNullOrWhiteSpace($name)) {
            continue
        }

        # Match one or more spaces followed by "(Simplified)"
        if ($name -match '^(.*?)\s+\(Simplified\)$') {

            $originalName = $matches[1].TrimEnd()

            # Only remove simplified version if the original exists too
            if ($subtitleNames -contains $originalName) {

                Write-Host "  Matched pair:" -ForegroundColor Yellow
                Write-Host "    Original:   $originalName"
                Write-Host "    Simplified: $name"

                $removeTrackIds += $track.id
            }
            else {
                Write-Host "  Simplified-looking track has no matching original:" -ForegroundColor DarkYellow
                Write-Host "    $name"
                Write-Host "  Leaving it untouched."
            }
        }
    }

    if ($removeTrackIds.Count -eq 0) {
        Write-Host "  No matching original + simplified pairs found. Skipping." -ForegroundColor DarkGray
        continue
    }

    # Keep every subtitle track except those confirmed above
    $keepSubtitleIds = @(
        $subtitleTracks |
        Where-Object {
            $_.id -notin $removeTrackIds
        } |
        ForEach-Object {
            $_.id
        }
    )

    # Write cleaned MKV into output subfolder
    $outputFile = Join-Path $outputDirectory $file.Name

    $arguments = @(
        "-o", $outputFile
    )

    if ($keepSubtitleIds.Count -gt 0) {
        $arguments += "--subtitle-tracks"
        $arguments += ($keepSubtitleIds -join ",")
    }
    else {
        $arguments += "--no-subtitles"
    }

    $arguments += $file.FullName

    Write-Host "  Removing $($removeTrackIds.Count) confirmed simplified subtitle track(s)..."
    Write-Host "  Output: $outputFile"

    & $mkvmerge @arguments

    if ($LASTEXITCODE -gt 1) {

        Write-Host "  ERROR: mkvmerge failed." -ForegroundColor Red

        if (Test-Path $outputFile) {
            Remove-Item $outputFile -Force
        }

        continue
    }

    if (-not (Test-Path $outputFile)) {
        Write-Host "  ERROR: Output file was not created." -ForegroundColor Red
        continue
    }

    Write-Host "  Done." -ForegroundColor Green
}

Write-Host ""
Write-Host "Finished."
Write-Host "Cleaned files are in:"
Write-Host "  $outputDirectory"
pause