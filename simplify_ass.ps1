# Requires Windows PowerShell 5.1+ or PowerShell 7, Python 3 and MKVToolNix.
# Put the current simplify_ass.py beside this script, or supply -Simplifier.
# Level 1 uses embedded fonts; install once: python -m pip install Pillow fonttools
# Level 2 is deprecated; its parameter remains for compatibility.
# Default: add tracks above 50,000 bytes with more than 10% fewer events.
# Use -ProcessAllTracks to bypass both thresholds; -ReplaceOriginals to replace.
param(
    [string] $InputFolder,
    [string] $OutputFolder,
    [string] $Simplifier,
    # Level 2 is deprecated and retained for explicit legacy calls only.
    [ValidateSet(1, 2)] [int] $SimplificationLevel = 1,
    [string] $Python = 'python',
    [string] $MkvToolNixFolder,
    [switch] $Recurse,
    [switch] $AddSimplifiedSubtitles = $true,
    [switch] $ReplaceOriginals,
    [switch] $ProcessAllTracks,
    [ValidateRange(0, 2147483647)] [long] $MinimumSubtitleBytes = 50000,
    [ValidateRange(0, 100)] [double] $MinimumEventReductionPercent = 10,
    [ValidateRange(0, 2147483647)] [int] $ScrollConcurrencyLimit = 32,
    [string] $ReportPath
)

# Normalize scrolling-text counters independently of console logs. Ordinary copies
# merged away are not counted as dropped text. Older scripts may omit the data.
function Get-ScrollingDropWarning([object] $Stats) {
    if ($null -eq $Stats -or $null -eq $Stats.prototype_scrolling_events_removed -or
        [long]$Stats.prototype_scrolling_events_removed -le 0) { return $null }
    $limit = $Stats.prototype_scrolling_concurrency_limit
    $limitText = if ($null -ne $limit) { [string]$limit } else { 'unknown' }
    return [pscustomobject]@{
        Code = 'scrolling_text_dropped'; Events = [long]$Stats.prototype_scrolling_events_removed
        Limit = $limit; Blocks = $Stats.prototype_scrolling_blocks_removed
        Peak = $Stats.prototype_scrolling_peak_after_reduction
        Message = "Dropped $($Stats.prototype_scrolling_events_removed) events due to exceeding concurrent event limit $limitText for scrolling text blocks."
    }
}

function Show-ScrollingDropWarning([object] $Warning, [string] $Context) {
    Write-Host ''
    Write-Host ('=' * 78) -ForegroundColor Red
    Write-Host ("WARNING: " + $Warning.Message) -ForegroundColor Red
    if ($Context) { Write-Host $Context -ForegroundColor Red }
    Write-Host ('=' * 78) -ForegroundColor Red
}

function Show-ScrollingDropSummary($Items) {
    $valid = @($Items | Where-Object { $null -ne $_ -and [long]$_.Events -gt 0 })
    foreach ($group in @($valid | Group-Object Limit)) {
        $events = [long]0
        foreach ($item in $group.Group) { $events += [long]$item.Events }
        $limit = $group.Group[0].Limit
        $limitText = if ($null -ne $limit) { [string]$limit } else { 'unknown' }
        Show-ScrollingDropWarning ([pscustomobject]@{
            Message = "Dropped $events events due to exceeding concurrent event limit $limitText for scrolling text blocks."
        }) ("RUN SUMMARY: $($group.Count) affected subtitle track(s).")
    }
}

# Probe once in the parent, rather than once per worker or track. Explicit
# overrides fail clearly on an old simplifier; default runs remain compatible.
function Get-SimplifierHelp([string] $PythonPath, [string] $SimplifierPath) {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $helpLines = @(& $PythonPath $SimplifierPath --help 2>&1)
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    if ($code -ne 0) { throw 'Cannot read simplifier command-line options.' }
    return ($helpLines -join "`n")
}

$ErrorActionPreference = 'Stop'
if ($ReplaceOriginals) { $AddSimplifiedSubtitles = $false }
if (-not $InputFolder) { $InputFolder = (Get-Location).Path }
if (-not $Simplifier) {
    $Simplifier = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'simplify_ass.py'
}

function Resolve-Executable([string] $Name) {
    if ($MkvToolNixFolder) {
        $candidate = Join-Path $MkvToolNixFolder ($Name + '.exe')
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
        throw "Cannot find $candidate"
    }
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidate = Join-Path $env:ProgramFiles ("MKVToolNix\" + $Name + '.exe')
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    throw "Cannot find $Name. Install MKVToolNix or pass -MkvToolNixFolder."
}

function Check-Exit([string] $Step) {
    # MKVToolNix uses 1 for warnings and 2 for errors. Warnings still need review.
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit code $LASTEXITCODE)." }
}

function Flag([object] $Value) {
    if ($Value) { return '1' }
    return '0'
}

$inputRoot = (Resolve-Path -LiteralPath $InputFolder).Path.TrimEnd('\', '/')
if (-not (Test-Path -LiteralPath $inputRoot -PathType Container)) { throw 'InputFolder must be a folder.' }
if (-not $OutputFolder) { $OutputFolder = Join-Path $inputRoot 'output' }
$outputRoot = [IO.Path]::GetFullPath($OutputFolder).TrimEnd('\', '/')
if ($outputRoot -ieq $inputRoot) { throw 'OutputFolder must differ from InputFolder.' }
$simplifierPath = (Resolve-Path -LiteralPath $Simplifier).Path
$mkvmerge = Resolve-Executable 'mkvmerge'
$mkvextract = Resolve-Executable 'mkvextract'
$pythonCmd = Get-Command $Python -ErrorAction SilentlyContinue
if (-not $pythonCmd) { throw "Cannot find Python command: $Python" }
$pythonPath = $pythonCmd.Source
$simplifierHelp = Get-SimplifierHelp $pythonPath $simplifierPath
$supportsScrollLimit = $simplifierHelp -match '(?m)(?:^|\s)--scroll-concurrency-limit(?:\s|=|$)'
$supportsStats = $simplifierHelp -match '(?m)(?:^|\s)--stats-json(?:\s|=|$)'
$supportsSuffix = $simplifierHelp -match '(?m)(?:^|\s)--suffix(?:\s|=|$)'
if ($PSBoundParameters.ContainsKey('ScrollConcurrencyLimit') -and -not $supportsScrollLimit) {
    throw 'This simplifier does not support -ScrollConcurrencyLimit. Select simplify_ass.py version 101 or newer with -Simplifier.'
}
if (-not $supportsStats) { throw 'This wrapper requires a simplifier with --stats-json support.' }
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

$files = @(Get-ChildItem -LiteralPath $inputRoot -Filter '*.mkv' -File -Recurse:$Recurse |
    Where-Object { -not $_.FullName.StartsWith($outputRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) })
if (-not $files.Count) { Write-Host 'No MKV files found.'; return }

$failures = 0
$fontDependenciesChecked = $false
$conversionTracks = [System.Collections.Generic.List[object]]::new()
$droppedTextTracks = [System.Collections.Generic.List[object]]::new()
try {
foreach ($file in $files) {
    $relative = $file.FullName.Substring($inputRoot.Length).TrimStart('\', '/')
    $destination = Join-Path $outputRoot $relative
    $parent = Split-Path -Parent $destination
    if (Test-Path -LiteralPath $destination) {
        Write-Warning "Already exists; skipping: $destination"
        continue
    }
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $work = Join-Path ([IO.Path]::GetTempPath()) ('ass-remux-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $work | Out-Null
    $partial = Join-Path $parent ($file.BaseName + '.' + [guid]::NewGuid().ToString('N') + '.partial.mkv')

    try {
        Write-Host "Processing: $($file.FullName)"
        $jsonLines = & $mkvmerge -J $file.FullName
        Check-Exit 'mkvmerge identification'
        $info = ($jsonLines -join "`n" | ConvertFrom-Json)
        $assTracks = @($info.tracks | Where-Object {
            $_.type -eq 'subtitles' -and $_.properties.codec_id -in @('S_TEXT/ASS', 'S_TEXT/SSA')
        })
        if (-not $assTracks.Count) {
            Copy-Item -LiteralPath $file.FullName -Destination $destination -ErrorAction Stop
            Write-Host "  No ASS/SSA tracks; copied unchanged."
            continue
        }

        $candidates = @()
        foreach ($track in $assTracks) {
            $ext = if ($track.properties.codec_id -eq 'S_TEXT/SSA') { '.ssa' } else { '.ass' }
            $extracted = Join-Path $work ("track-$($track.id)" + $ext)
            & $mkvextract $file.FullName tracks ("$($track.id):$extracted")
            Check-Exit "extract track $($track.id)"
            if (-not (Test-Path -LiteralPath $extracted -PathType Leaf)) { throw "Track $($track.id) was not extracted." }
            $size = (Get-Item -LiteralPath $extracted).Length
            if (-not $ProcessAllTracks -and $size -le $MinimumSubtitleBytes) {
                Write-Host "  Track $($track.id): skipped size threshold ($size bytes; requires more than $MinimumSubtitleBytes)."
                continue
            }
            $simple = Join-Path $work ("track-$($track.id).simple" + $ext)
            $candidates += [pscustomobject]@{ Original = $track; Input = $extracted; File = $simple }
        }
        if (-not $candidates.Count) {
            Copy-Item -LiteralPath $file.FullName -Destination $destination -ErrorAction Stop
            Write-Host '  No tracks above size threshold; copied unchanged.'
            continue
        }

        if ($SimplificationLevel -eq 1 -and -not $fontDependenciesChecked) {
            & $pythonPath -c "import PIL.ImageFont; import fontTools.ttLib"
            if ($LASTEXITCODE -ne 0) {
                throw 'Font spacing needs Pillow and fonttools in this Python installation. Run: python -m pip install Pillow fonttools'
            }
            $fontDependenciesChecked = $true
        }

        # Extract fonts once per MKV using the already-resolved MKVToolNix
        # executable. This also works when MKVToolNix is not in Python's PATH.
        $fontsFolder = Join-Path $work 'fonts'
        $fontTargets = @()
        if ($SimplificationLevel -eq 1) {
            New-Item -ItemType Directory -Path $fontsFolder | Out-Null
            foreach ($attachment in @($info.attachments)) {
                if ($null -eq $attachment) { continue }
                $suffix = [IO.Path]::GetExtension([string]$attachment.file_name).ToLowerInvariant()
                $mime = ([string]$attachment.content_type).ToLowerInvariant()
                if ($suffix -notin @('.ttf', '.otf', '.ttc', '.otc')) {
                    if ($mime -notin @('application/x-truetype-font', 'application/vnd.ms-opentype',
                        'application/x-font-ttf', 'application/x-font-opentype',
                        'font/ttf', 'font/otf', 'font/collection', 'application/font-sfnt')) { continue }
                    $suffix = if ($mime -eq 'font/collection') { '.ttc' } else { '.ttf' }
                }
                # Numeric filenames avoid unsafe paths from attachment names.
                $attachmentId = [int]$attachment.id
                $fontPath = Join-Path $fontsFolder ("font-$attachmentId" + $suffix)
                $fontTargets += [pscustomobject]@{ Id = $attachmentId; File = $fontPath }
            }
            if ($fontTargets.Count) {
                $fontArgs = @($file.FullName, 'attachments')
                $fontArgs += @($fontTargets | ForEach-Object { "$($_.Id):$($_.File)" })
                & $mkvextract @fontArgs
                Check-Exit 'extract embedded fonts'
                foreach ($target in $fontTargets) {
                    if (-not (Test-Path -LiteralPath $target.File -PathType Leaf)) {
                        throw "Font attachment $($target.Id) was not extracted."
                    }
                }
                Write-Host "  Extracted $($fontTargets.Count) font attachment(s)."
            } else {
                Write-Host '  No attached fonts; Python will check installed fonts.'
            }
        }

        $replacements = @()
        $pythonArgs = @($simplifierPath, '--level', [string]$SimplificationLevel)
        if ($SimplificationLevel -eq 1) { $pythonArgs += @('--fonts-dir', $fontsFolder) }
        if ($supportsScrollLimit) { $pythonArgs += @('--scroll-concurrency-limit', [string]$ScrollConcurrencyLimit) }
        if ($supportsSuffix) { $pythonArgs += @('--suffix', '.simple') }
        $statsPath = Join-Path $work 'simplification-stats.json'
        $pythonArgs += @('--stats-json', $statsPath)
        $pythonArgs += '--'
        $pythonArgs += @($candidates | ForEach-Object { $_.Input })

        # One Python process reuses the font index across every subtitle track.
        & $pythonPath @pythonArgs
        Check-Exit 'simplify subtitle tracks'
        if (-not (Test-Path -LiteralPath $statsPath -PathType Leaf)) { throw 'Simplifier did not create its statistics JSON.' }
        $statsReport = Get-Content -LiteralPath $statsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($candidate in $candidates) {
            if (-not (Test-Path -LiteralPath $candidate.File -PathType Leaf)) {
                throw "Missing simplified track: $($candidate.File)"
            }
            $records = @($statsReport.tracks | Where-Object { $_.input -ieq [IO.Path]::GetFullPath($candidate.Input) })
            if ($records.Count -ne 1 -or $records[0].error -or $null -eq $records[0].stats) {
                throw "Missing or invalid simplifier statistics for track $($candidate.Original.id)."
            }
            $stats = $records[0].stats
            $trackReport = [pscustomobject]@{
                File = $file.FullName; Output = $destination; Track = $candidate.Original.id
                Name = $candidate.Original.properties.track_name; Stats = $stats
                Warnings = @($records[0].warnings | Where-Object { $null -ne $_ })
                SelectedForRemux = $false
            }
            $conversionTracks.Add($trackReport)
            $warning = Get-ScrollingDropWarning $stats
            if ($null -ne $warning) {
                $droppedTextTracks.Add([pscustomobject]@{
                    File = $file.FullName; Track = $candidate.Original.id; Name = $candidate.Original.properties.track_name
                    Events = $warning.Events; Limit = $warning.Limit; Blocks = $warning.Blocks
                    Peak = $warning.Peak; Message = $warning.Message
                })
                Show-ScrollingDropWarning $warning ("$($file.Name) - track $($candidate.Original.id) - $($candidate.Original.properties.track_name)")
            }
            if (-not $ProcessAllTracks) {
                if ($null -eq $stats -or $null -eq $stats.original -or $null -eq $stats.output -or
                    [long]$stats.original -lt 0 -or [long]$stats.output -lt 0) {
                    throw "Missing or invalid event counts for track $($candidate.Original.id)."
                }
                $reduction = if ([long]$stats.original -gt 0) {
                    100.0 * ([long]$stats.original - [long]$stats.output) / [long]$stats.original
                } else { 0.0 }
                if ($reduction -le $MinimumEventReductionPercent) {
                    Write-Host ("  Track {0}: skipped reduction threshold ({1:N1}% fewer events; requires more than {2}%)." -f
                        $candidate.Original.id, $reduction, $MinimumEventReductionPercent)
                    continue
                }
            }
            $trackReport.SelectedForRemux = $true
            $replacements += $candidate
        }
        if (-not $replacements.Count) {
            Copy-Item -LiteralPath $file.FullName -Destination $destination -ErrorAction Stop
            Write-Host '  No tracks passed the reduction threshold; copied unchanged.'
            continue
        }

        $ids = ($replacements | ForEach-Object { $_.Original.id }) -join ','
        $mergeArgs = [System.Collections.Generic.List[string]]::new()
        $mergeArgs.Add('-o'); $mergeArgs.Add($partial)
        if (-not $AddSimplifiedSubtitles) {
            if (@($info.tracks | Where-Object { $_.type -eq 'subtitles' }).Count -eq $replacements.Count) {
                $mergeArgs.Add('--no-subtitles')
            } else {
                $mergeArgs.Add('--subtitle-tracks'); $mergeArgs.Add('!' + $ids)
            }
        }
        $mergeArgs.Add($file.FullName)

        foreach ($replacement in $replacements) {
            $properties = $replacement.Original.properties
            $language = if ($properties.language_ietf) { $properties.language_ietf } else { $properties.language }
            if ($language) { $mergeArgs.Add('--language'); $mergeArgs.Add('0:' + $language) }
            if ($AddSimplifiedSubtitles) {
                $newName = if ($properties.track_name) { $properties.track_name + ' (Simplified)' } else { 'Simplified' }
                $mergeArgs.Add('--track-name'); $mergeArgs.Add('0:' + $newName)
                # Keep the original as the automatically selected track.
                $mergeArgs.Add('--default-track-flag'); $mergeArgs.Add('0:0')
                $mergeArgs.Add('--forced-display-flag'); $mergeArgs.Add('0:0')
            } else {
                if ($properties.track_name) { $mergeArgs.Add('--track-name'); $mergeArgs.Add('0:' + $properties.track_name) }
                if ($null -ne $properties.default_track) { $mergeArgs.Add('--default-track-flag'); $mergeArgs.Add('0:' + (Flag $properties.default_track)) }
                if ($null -ne $properties.forced_track) { $mergeArgs.Add('--forced-display-flag'); $mergeArgs.Add('0:' + (Flag $properties.forced_track)) }
            }
            if ($null -ne $properties.enabled_track) { $mergeArgs.Add('--track-enabled-flag'); $mergeArgs.Add('0:' + (Flag $properties.enabled_track)) }
            $extraFlags = @{
                flag_hearing_impaired = '--hearing-impaired-flag'
                flag_visual_impaired = '--visual-impaired-flag'
                flag_text_descriptions = '--text-descriptions-flag'
                flag_original = '--original-flag'
                flag_commentary = '--commentary-flag'
            }
            foreach ($key in $extraFlags.Keys) {
                $value = $properties.$key
                if ($null -ne $value) { $mergeArgs.Add($extraFlags[$key]); $mergeArgs.Add('0:' + (Flag $value)) }
            }
            $mergeArgs.Add($replacement.File)
        }

        # Input 0 is the original MKV; inputs 1+ are simplified subtitle files.
        $order = @()
        foreach ($track in $info.tracks) {
            $index = -1
            for ($i = 0; $i -lt $replacements.Count; $i++) {
                if ($replacements[$i].Original.id -eq $track.id) { $index = $i; break }
            }
            if ($index -ge 0 -and $AddSimplifiedSubtitles) {
                $order += "0:$($track.id)"
                $order += "$(($index + 1)):0"
            } elseif ($index -ge 0) { $order += "$(($index + 1)):0" }
            else { $order += "0:$($track.id)" }
        }
        $mergeArgs.Add('--track-order'); $mergeArgs.Add(($order -join ','))
        & $mkvmerge @mergeArgs
        Check-Exit 'mkvmerge remux'
        if (-not (Test-Path -LiteralPath $partial -PathType Leaf)) { throw 'Remux did not create an MKV.' }
        $outputInfo = ((& $mkvmerge -J $partial) -join "`n" | ConvertFrom-Json)
        Check-Exit 'output validation'
        $expectedTracks = @($info.tracks).Count
        if ($AddSimplifiedSubtitles) { $expectedTracks += $replacements.Count }
        if (@($outputInfo.tracks).Count -ne $expectedTracks) { throw 'Output track count differs from expected count.' }
        Move-Item -LiteralPath $partial -Destination $destination -ErrorAction Stop
        if ($AddSimplifiedSubtitles) {
            Write-Host "  Saved: $destination ($($replacements.Count) simplified track(s) added)"
        } else {
            Write-Host "  Saved: $destination ($($replacements.Count) ASS/SSA track(s) simplified)"
        }
    } catch {
        $failures++
        Write-Warning "Failed: $($file.FullName): $_"
        if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
    } finally {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
}
} finally {
Show-ScrollingDropSummary $droppedTextTracks.ToArray()
if ($ReportPath) {
    $reportFullPath = [IO.Path]::GetFullPath($ReportPath)
    $reportFolder = [IO.Path]::GetDirectoryName($reportFullPath)
    New-Item -ItemType Directory -Path $reportFolder -Force | Out-Null
    [pscustomobject]@{
        Simplifier = $simplifierPath; Level = $SimplificationLevel; Failures = $failures
        ScrollConcurrencyLimit = if ($supportsScrollLimit) { $ScrollConcurrencyLimit } else { $null }
        ScrollingDropWarnings = @($droppedTextTracks.ToArray())
        Tracks = @($conversionTracks.ToArray())
    } | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $reportFullPath -Encoding UTF8
    Write-Host "Report: $reportFullPath"
}
}
if ($failures) { throw "$failures file(s) failed. See warnings above." }
