$ErrorActionPreference = "Stop"

# ------------------------------------------------------------
# Requirements
# ------------------------------------------------------------

if (-not (Get-Command mkvmerge -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: mkvmerge.exe was not found in PATH." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

$files = Get-ChildItem -Path . -Filter *.mkv -File

if (-not $files) {
    Write-Host "No MKV files found in the current folder."
    Read-Host "Press Enter to exit"
    exit
}

# ------------------------------------------------------------
# Scan all subtitle names
# ------------------------------------------------------------

$subtitleNames = New-Object System.Collections.Generic.List[string]

Write-Host ""
Write-Host "Scanning MKV files..." -ForegroundColor Cyan

foreach ($file in $files) {

    Write-Host "  $($file.Name)"

    try {
        $json = & mkvmerge -J $file.FullName | ConvertFrom-Json
    }
    catch {
        Write-Host "    ERROR: Could not read file." -ForegroundColor Red
        continue
    }

    foreach ($track in $json.tracks) {

        if ($track.type -ne "subtitles") {
            continue
        }

        $name = $track.properties.track_name

        if ([string]::IsNullOrEmpty($name)) {
            $name = "(unnamed)"
        }

        if (-not $subtitleNames.Contains($name)) {
            $subtitleNames.Add($name)
        }
    }
}

if ($subtitleNames.Count -eq 0) {
    Write-Host ""
    Write-Host "No subtitle tracks found."
    Read-Host "Press Enter to exit"
    exit
}

$subtitleNames = @($subtitleNames | Sort-Object)

# ------------------------------------------------------------
# Show merged list
# ------------------------------------------------------------

Write-Host ""
Write-Host "Subtitle tracks found:" -ForegroundColor Cyan
Write-Host ""

for ($i = 0; $i -lt $subtitleNames.Count; $i++) {
    Write-Host ("{0,3}. {1}" -f ($i + 1), $subtitleNames[$i])
}

Write-Host ""
Write-Host "Enter one or more numbers separated by commas."
Write-Host "Example: 2,4,7"
Write-Host ""

$selection = Read-Host "Tracks to remove"

# ------------------------------------------------------------
# Parse selections
# ------------------------------------------------------------

$selectedNumbers = @()

foreach ($part in ($selection -split ",")) {

    $part = $part.Trim()

    [int]$number = 0

    if (-not [int]::TryParse($part, [ref]$number)) {
        Write-Host "Invalid selection: $part" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }

    if ($number -lt 1 -or $number -gt $subtitleNames.Count) {
        Write-Host "Selection out of range: $number" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }

    if ($selectedNumbers -notcontains $number) {
        $selectedNumbers += $number
    }
}

$selectedNames = @()

foreach ($number in $selectedNumbers) {
    $selectedNames += $subtitleNames[$number - 1]
}

# ------------------------------------------------------------
# Confirmation
# ------------------------------------------------------------

Write-Host ""
Write-Host "Selected subtitle names:" -ForegroundColor Yellow

foreach ($name in $selectedNames) {
    Write-Host "  - $name"
}

Write-Host ""

$confirm = Read-Host "Remove these subtitles from all MKV files? (Y/N)"

if ($confirm -notmatch '^[Yy]$') {
    Write-Host "Cancelled."
    exit
}

# ------------------------------------------------------------
# Create output directory
# ------------------------------------------------------------

$outputDir = Join-Path $PWD "output"

if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir | Out-Null
}

# ------------------------------------------------------------
# Process each MKV
# ------------------------------------------------------------

$changed = 0
$notFound = 0
$failed = 0

Write-Host ""
Write-Host "Processing..." -ForegroundColor Cyan
Write-Host ""

foreach ($file in $files) {

    Write-Host "File: $($file.Name)"

    try {
        $json = & mkvmerge -J $file.FullName | ConvertFrom-Json
    }
    catch {
        Write-Host "  ERROR: Could not read file." -ForegroundColor Red
        $failed++
        continue
    }

    $tracksToRemove = @()
    $matchedNames = @()

    foreach ($track in $json.tracks) {

        if ($track.type -ne "subtitles") {
            continue
        }

        $name = $track.properties.track_name

        if ([string]::IsNullOrEmpty($name)) {
            $name = "(unnamed)"
        }

        # Match by NAME for this specific file.
        if ($selectedNames -ccontains $name) {
            $tracksToRemove += $track.id

            if ($matchedNames -cnotcontains $name) {
                $matchedNames += $name
            }
        }
    }

    if ($tracksToRemove.Count -eq 0) {
        Write-Host "  None of the selected subtitles are present - skipped."
        $notFound++
        Write-Host ""
        continue
    }

    Write-Host "  Removing:"
    foreach ($name in $matchedNames) {
        Write-Host "    - $name"
    }

    Write-Host "  Matching track ID(s): $($tracksToRemove -join ', ')"

    $outputFile = Join-Path $outputDir $file.Name

    # Exclude all matching subtitle track IDs in one remux.
    $trackList = $tracksToRemove -join ","
    $excludeArgument = "!$trackList"

    $arguments = @(
        "-o"
        $outputFile
        "--subtitle-tracks"
        $excludeArgument
        $file.FullName
    )

    & mkvmerge @arguments

    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Removed successfully." -ForegroundColor Green
        $changed++
    }
    else {
        Write-Host "  ERROR: mkvmerge failed." -ForegroundColor Red

        if (Test-Path $outputFile) {
            Remove-Item $outputFile -Force
        }

        $failed++
    }

    Write-Host ""
}

# ------------------------------------------------------------
# Summary
# ------------------------------------------------------------

Write-Host "----------------------------------------"
Write-Host "Finished"
Write-Host "----------------------------------------"

Write-Host "Selected subtitle names:"
foreach ($name in $selectedNames) {
    Write-Host "  - $name"
}

Write-Host ""
Write-Host "Files changed: $changed"
Write-Host "No matches:    $notFound"
Write-Host "Failed:        $failed"
Write-Host ""
Write-Host "Modified files are in:"
Write-Host $outputDir
Write-Host ""

Read-Host "Press Enter to exit"