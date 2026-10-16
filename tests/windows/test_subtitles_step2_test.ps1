# Test locally cached ASS/SSA and fonts. Windows PowerShell 5.1+; Python and simplify_ass.py required.
# InputFolder is the output folder of extract_mkv_test_data.ps1. No MKVToolNix or NAS access needed.
param(
    [string] $InputFolder,
    [string] $OutputFolder,
    [string] $Simplifier,
    # Legacy simplification is deprecated and retained for explicit legacy calls only.
    [ValidateSet(1, 2)] [int] $SimplificationLevel = 1,
    [string] $Python = 'python',
    [ValidateRange(1, 128)] [int] $MaxParallel = [Math]::Min(4, [Environment]::ProcessorCount),
    [switch] $NoFontSpacing,
    [string] $Encoding,
    [ValidateRange(0, 2147483647)] [Nullable[int]] $ScrollConcurrencyLimit,
    [ValidateScript({ $_ -ge 0 -and -not [double]::IsNaN($_) -and -not [double]::IsInfinity($_) })]
    [Nullable[double]] $ColorPhaseMinHold,
    [ValidateScript({ $_ -ge 0 -and -not [double]::IsNaN($_) -and -not [double]::IsInfinity($_) })]
    [Nullable[double]] $ColorPhaseChangeInterval
)

. (Join-Path $PSScriptRoot 'subtitle_report_helpers.ps1')

# Normalize scrolling-text counters independently of console logs. Ordinary copies
# merged away are not counted as dropped text. Older scripts may omit the data.
# Normalize older report keys at the reporting boundary. Current keys win.
function ConvertTo-CurrentSubtitleStats([object] $Stats) {
    if ($null -eq $Stats) { return $null }
    $aliases = @{
        'aggressive_copies' = 'stacked_text_copies_flattened'
        'aggressive_sequences' = 'text_effect_sequences_frozen'
        'prototype_vector_candidates' = 'drawing_candidates'
        'prototype_strips_collapsed' = 'drawing_strips_collapsed'
        'prototype_vector_duplicates' = 'drawing_duplicates_removed'
        'prototype_fade_frames' = 'drawing_fade_frames_removed'
        'prototype_unsupported_drawings' = 'unsupported_drawings_excluded'
        'prototype_polygons_simplified' = 'drawing_contours_simplified'
        'prototype_held_scaling_exits' = 'drawing_scale_exits_frozen'
        'prototype_held_move_entrances' = 'drawing_move_entrances_frozen'
        'prototype_edge_slivers_detached' = 'drawing_edge_slivers_detached'
        'prototype_composite_backdrops' = 'composite_backdrops_built'
        'prototype_scrolling_events_removed' = 'scrolling_events_dropped'
        'prototype_scrolling_blocks_detected' = 'scrolling_blocks_detected'
        'prototype_scrolling_blocks_removed' = 'scrolling_blocks_dropped'
        'prototype_scrolling_blocks_retained' = 'scrolling_blocks_retained'
        'prototype_scrolling_peak_after_reduction' = 'scrolling_peak_after_reduction'
        'prototype_scrolling_concurrency_limit' = 'scrolling_concurrency_limit'
        'prototype_masked_foregrounds_restored' = 'masked_foregrounds_restored'
        'prototype_shadow_offsets_repaired' = 'shadow_offsets_repaired'
        'prototype_vectors_capped' = 'drawing_events_capped'
        'prototype_unmeasured_backdrops' = 'unmeasured_backdrops_retained'
        'prototype_supports_retained' = 'supporting_shapes_retained'
        'prototype_textures_removed' = 'font_textures_removed'
        'prototype_fullscreen_backgrounds' = 'fullscreen_backgrounds_retained'
        'prototype_adjacent_shapes' = 'adjacent_shapes_retained'
    }
    $values = [ordered]@{}
    foreach ($property in $Stats.PSObject.Properties) {
        if (-not $aliases.ContainsKey($property.Name)) {
            $values[$property.Name] = $property.Value
        }
    }
    foreach ($old in $aliases.Keys) {
        $property = $Stats.PSObject.Properties[$old]
        $current = $aliases[$old]
        if ($null -ne $property -and -not $values.Contains($current)) {
            $values[$current] = $property.Value
        }
    }
    return [pscustomobject]$values
}

function Get-ScrollingDropWarning([object] $Stats) {
    $Stats = ConvertTo-CurrentSubtitleStats $Stats
    if ($null -eq $Stats -or $null -eq $Stats.scrolling_events_dropped -or
        [long]$Stats.scrolling_events_dropped -le 0) { return $null }
    $limit = $Stats.scrolling_concurrency_limit
    $limitText = if ($null -ne $limit) { [string]$limit } else { 'unknown' }
    return [pscustomobject]@{
        Code = 'scrolling_text_dropped'; Events = [long]$Stats.scrolling_events_dropped
        Limit = $limit; Blocks = $Stats.scrolling_blocks_dropped
        Peak = $Stats.scrolling_peak_after_reduction
        Message = "Dropped $($Stats.scrolling_events_dropped) events due to exceeding concurrent event limit $limitText for scrolling text blocks."
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
if (-not $InputFolder) { $InputFolder = (Get-Location).Path }
$Simplifier = Resolve-SubtitleSimplifier -ScriptRoot $PSScriptRoot -Simplifier $Simplifier

function Normalize-Folder([string] $Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -eq [IO.Path]::GetPathRoot($full)) { return $full }
    return $full.TrimEnd('\', '/')
}

$inputRoot = Normalize-Folder (Resolve-Path -LiteralPath $InputFolder).Path
if (-not (Test-Path -LiteralPath $inputRoot -PathType Container)) { throw 'InputFolder must be a folder.' }
if (-not $OutputFolder) { $OutputFolder = Join-Path $inputRoot 'subtitle_test_output' }
$outputRoot = Normalize-Folder $OutputFolder
if ($outputRoot -ieq $inputRoot) { throw 'OutputFolder must differ from InputFolder.' }
$simplifierPath = (Resolve-Path -LiteralPath $Simplifier).Path
$simplifierHash = (Get-FileHash -LiteralPath $simplifierPath -Algorithm SHA256).Hash
$pythonCommand = Get-Command $Python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pythonCommand) { throw "Cannot find Python command: $Python" }
$pythonPath = $pythonCommand.Source
$simplifierHelp = Get-SimplifierHelp $pythonPath $simplifierPath
$simplifierVersion = Get-SubtitleSimplifierVersion $pythonPath $simplifierPath
$supportsColorPhases = $simplifierHelp.Contains('--color-phase-min-hold') -and $simplifierHelp.Contains('--color-phase-change-interval')
if (($PSBoundParameters.ContainsKey('ColorPhaseMinHold') -or $PSBoundParameters.ContainsKey('ColorPhaseChangeInterval')) -and -not $supportsColorPhases) {
    throw 'This simplifier does not support color phase settings. Use v209 or newer.'
}
$supportsScrollLimit = $simplifierHelp -match '(?m)(?:^|\s)--scroll-concurrency-limit(?:\s|=|$)'
if ($PSBoundParameters.ContainsKey('ScrollConcurrencyLimit') -and -not $supportsScrollLimit) {
    throw 'This simplifier does not support -ScrollConcurrencyLimit. Select simplify_ass.py version 101 or newer with -Simplifier.'
}

# Dependencies are optional in the current simplifier. Do not block basic tests.
if ($SimplificationLevel -eq 1 -and -not $NoFontSpacing) {
    $probe = @'
import importlib.util
missing = [m for m in ('PIL', 'fontTools') if importlib.util.find_spec(m) is None]
if missing:
    print('Font spacing unavailable: install Pillow fonttools uharfbuzz.')
else:
    from PIL import features
    if not features.check_feature('raqm') and importlib.util.find_spec('uharfbuzz') is None:
        print('RAQM unavailable: install uharfbuzz for measured word spacing.')
'@
    $probeOutput = @(& $pythonPath -c $probe)
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency check failed.' }
    foreach ($message in $probeOutput) { Write-Warning $message }
}

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
$runRoot = Join-Path $outputRoot ('run-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' +
                                  [guid]::NewGuid().ToString('N').Substring(0, 6))
New-Item -ItemType Directory -Path $runRoot | Out-Null
$reportPath = Join-Path $runRoot 'report.txt'
$jsonReportPath = Join-Path $runRoot 'report.json'
$outputPrefix = $outputRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
$files = @(Get-ChildItem -LiteralPath $inputRoot -Filter 'manifest.json' -File -Recurse |
    Where-Object { -not $_.FullName.StartsWith($outputPrefix, [StringComparison]::OrdinalIgnoreCase) } |
    Sort-Object FullName)
$workerCount = [Math]::Min($MaxParallel, $files.Count)
$startedAt = Get-Date
$completed = [System.Collections.Generic.List[object]]::new()
$active = [System.Collections.Generic.List[object]]::new()
$runState = 'Running'

$counterCatalog = Get-SubtitleCounterCatalog $SimplificationLevel
$labels = $counterCatalog.Labels

# Start-Job works on Windows PowerShell 5.1; no PS7 or ThreadJob module needed.
# Workers never write the aggregate report. All files and fonts are isolated.
$worker = {
    param($FilePath, $Relative, $ArchivePath, $SimplifierPath, $Level,
          $PythonPath, $DisableSpacing, $InputEncoding, $ScrollLimit, $SupportsScrollLimit, $PhaseHold, $PhaseInterval, $SupportsColorPhases)
    $ErrorActionPreference = 'Stop'
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $tracks = [System.Collections.Generic.List[object]]::new()
    $errors = [System.Collections.Generic.List[string]]::new()
    $warnings = [System.Collections.Generic.List[string]]::new()
    $otherTracks = 0
    $assCount = 0
    $fontCount = 0
    $work = $null
    $Destination = $null
    $archiveSaved = $false
    $stagingArchive = $null

    function Quote-NativeArgument([string] $Argument) {
        # Windows CRT quoting: double slashes before quotes and a closing quote.
        return '"' + [regex]::Replace([regex]::Replace($Argument, '(\\*)"', '$1$1\"'),
                                     '(\\+)$', '$1$1') + '"'
    }

    function Invoke-LoggedTool([string] $Executable, [string[]] $Arguments, [string] $LogName) {
        $prefix = Join-Path $Destination $LogName
        $argumentString = (@($Arguments | ForEach-Object { Quote-NativeArgument $_ }) -join ' ')
        ($Executable + ' ' + $argumentString) | Set-Content -LiteralPath ($prefix + '.command.txt') -Encoding UTF8
        $previousPreference = $ErrorActionPreference
        $previousIOEncoding = $env:PYTHONIOENCODING
        $previousUnbuffered = $env:PYTHONUNBUFFERED
        $previousConsoleEncoding = [Console]::OutputEncoding
        $locationPushed = $false
        try {
            Push-Location -LiteralPath $Destination
            $locationPushed = $true
            $env:PYTHONIOENCODING = 'utf-8'
            $env:PYTHONUNBUFFERED = '1'
            [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
            # Windows PS5 wraps native stderr in error records. Capture it without
            # treating warnings/tracebacks as terminating PowerShell errors.
            $ErrorActionPreference = 'Continue'
            $global:LASTEXITCODE = $null
            # A relative log filename avoids redirection treating [episode]
            # in an MKV directory name as a wildcard on Windows PowerShell.
            & $Executable @Arguments 2> ($LogName + '.stderr.log') |
                Out-File -LiteralPath ($prefix + '.stdout.log') -Encoding UTF8
            $code = $global:LASTEXITCODE
            if ($null -eq $code) { throw "Could not launch $Executable. See $LogName.stderr.log." }
            return [int]$code
        } finally {
            if ($locationPushed) { Pop-Location }
            $ErrorActionPreference = $previousPreference
            $env:PYTHONIOENCODING = $previousIOEncoding
            $env:PYTHONUNBUFFERED = $previousUnbuffered
            [Console]::OutputEncoding = $previousConsoleEncoding
        }
    }



    function Test-AlreadySimplified([string] $Path) {
        # Read comments, not track names. Older markers may precede Script Info.
        $reader = [IO.StreamReader]::new($Path, [Text.Encoding]::UTF8, $true)
        try {
            while ($null -ne ($line = $reader.ReadLine())) {
                if ($line -match '^\s*;\s*Simplified by simplify_ass\.py(?:\s|$)') { return $true }
            }
            return $false
        } finally { $reader.Dispose() }
    }

    # Keep temporary results until the finished ZIP has been delivered.
    try {
        try {
            $work = Join-Path ([IO.Path]::GetTempPath()) ('subtitle-test-' + [guid]::NewGuid().ToString('N'))
            New-Item -ItemType Directory -Path $work | Out-Null
            $Destination = Join-Path $work 'results'
            New-Item -ItemType Directory -Path $Destination | Out-Null
            $cacheRoot = [IO.Path]::GetDirectoryName($FilePath)
            $manifest = Get-Content -LiteralPath $FilePath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($manifest.Format -ne 'subtitle-test-cache' -or $manifest.Version -ne 1) {
                throw 'Unsupported cache manifest. Re-extract with extract_mkv_test_data.ps1.'
            }
            Copy-Item -LiteralPath $FilePath -Destination (Join-Path $Destination 'manifest.json')
            function Resolve-CacheFile([string] $Name) {
                if (-not $Name -or [IO.Path]::IsPathRooted($Name) -or
                    @($Name -split '[/\\]' | Where-Object { $_ -eq '..' }).Count) {
                    throw "Invalid cache entry path: $Name"
                }
                $path = Join-Path $cacheRoot $Name
                if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Cache entry missing: $Name" }
                return $path
            }
            $assCount = @($manifest.Tracks).Count
            $otherTracks = [int]$manifest.OtherTracks
            $fontsFolder = Join-Path $work 'fonts'
            [IO.Directory]::CreateDirectory($fontsFolder) | Out-Null
            if ($Level -eq 1 -and -not $DisableSpacing) {
                foreach ($font in @($manifest.Fonts)) {
                    $path = Resolve-CacheFile $font.File
                    Copy-Item -LiteralPath $path -Destination (Join-Path $fontsFolder ([IO.Path]::GetFileName($path)))
                    $fontCount++
                }
            }
            $entries = @()
            foreach ($track in @($manifest.Tracks)) {
                $extension = [IO.Path]::GetExtension([string]$track.File).ToLowerInvariant()
                if ($extension -notin @('.ass','.ssa')) { throw 'Cache contains a non-ASS/SSA track.' }
                $source = Join-Path $work ("track-$($track.Track)" + $extension)
                $entry = [pscustomobject]@{
                    Track = $track.Track; Name = $track.Name; Source = $source
                    ExpectedOutput = (Join-Path $work ("track-$($track.Track).simple" + $extension))
                    OriginalFile = (Join-Path $Destination ("track-$($track.Track).original" + $extension))
                    SimplifiedFile = (Join-Path $Destination ("track-$($track.Track).simple" + $extension))
                    Stats = $null; Warnings = @(); ProcessingSeconds = $null; Error = $null; Skipped = $false; SkipReason = $null
                }
                $tracks.Add($entry)
                try {
                    Copy-Item -LiteralPath (Resolve-CacheFile $track.File) -Destination $source
                    if (Test-AlreadySimplified $source) {
                        $entry.Skipped = $true
                        $entry.SkipReason = 'Already simplified by simplify_ass.py'
                        continue
                    }
                    Copy-Item -LiteralPath $source -Destination $entry.OriginalFile
                    $entries += $entry
                } catch {
                    $entry.Error = $_.Exception.Message
                    $errors.Add("Track $($entry.Track): $($entry.Error)")
                }
            }

            if ($entries.Count) {
                $statsPath = Join-Path $Destination 'stats.json'
                $arguments = @($SimplifierPath, '--level', [string]$Level, '--stats-json', $statsPath, '--suffix', '.simple')
                if ($SupportsScrollLimit -and $null -ne $ScrollLimit) { $arguments += @('--scroll-concurrency-limit', [string]$ScrollLimit) }
                if ($SupportsColorPhases -and $null -ne $PhaseHold) {
                    $arguments += @('--color-phase-min-hold', $PhaseHold.ToString([Globalization.CultureInfo]::InvariantCulture))
                }
                if ($SupportsColorPhases -and $null -ne $PhaseInterval) {
                    $arguments += @('--color-phase-change-interval', $PhaseInterval.ToString([Globalization.CultureInfo]::InvariantCulture))
                }
                if ($Level -eq 1 -and -not $DisableSpacing) { $arguments += @('--fonts-dir', $fontsFolder) }
                if ($DisableSpacing) { $arguments += '--no-font-spacing' }
                if ($InputEncoding) { $arguments += @('--encoding', $InputEncoding) }
                $arguments += '--'
                $arguments += @($entries | ForEach-Object { $_.Source })
                # Reuse the font index across all subtitle tracks in this MKV.
                $pythonCode = Invoke-LoggedTool $PythonPath $arguments 'simplifier'
                $data = $null
                if (Test-Path -LiteralPath $statsPath -PathType Leaf) {
                    try { $data = Get-Content -LiteralPath $statsPath -Raw -Encoding UTF8 | ConvertFrom-Json }
                    catch { $errors.Add("Invalid statistics JSON: $($_.Exception.Message)") }
                } else { $errors.Add('Simplifier did not create the statistics JSON.') }
                if ($null -ne $data -and @($data.tracks).Count -ne $entries.Count) {
                    $errors.Add('Statistics count differs from the number of extracted tracks.')
                }
                if ($pythonCode -ne 0) { $errors.Add("Simplifier returned exit code $pythonCode. See simplifier.stderr.log.") }
                foreach ($entry in $entries) {
                    try {
                        # Preserve a generated output even if its statistics were not written.
                        if (Test-Path -LiteralPath $entry.ExpectedOutput -PathType Leaf) {
                            Copy-Item -LiteralPath $entry.ExpectedOutput -Destination $entry.SimplifiedFile
                        }
                        $records = @($data.tracks | Where-Object { $_.input -ieq [IO.Path]::GetFullPath($entry.Source) })
                        if ($records.Count -ne 1) { throw 'Missing or duplicate track statistics.' }
                        if ($null -ne $records[0].processing_seconds) {
                            $seconds = [double]$records[0].processing_seconds
                            if ($seconds -ge 0 -and -not [double]::IsNaN($seconds) -and -not [double]::IsInfinity($seconds)) {
                                $entry.ProcessingSeconds = $seconds
                            }
                        }
                        $entry.Warnings = @($records[0].warnings | Where-Object { $null -ne $_ })
                        if ($records[0].error) { throw ([string]$records[0].error) }
                        if ($null -eq $records[0].stats -or $null -eq $records[0].stats.original -or
                            $null -eq $records[0].stats.output) { throw 'Missing event counts in track statistics.' }
                        if (-not (Test-Path -LiteralPath $entry.SimplifiedFile -PathType Leaf)) { throw 'Simplified output is missing.' }
                        $entry.Stats = $records[0].stats
                    } catch {
                        $entry.Error = $_.Exception.Message
                        $errors.Add("Track $($entry.Track): $($entry.Error)")
                    }
                }
            }
        } catch {
            $message = $_.Exception.Message
            $errors.Add($message)
            foreach ($entry in $tracks) {
                if (-not $entry.Skipped -and $null -eq $entry.Stats -and -not $entry.Error) { $entry.Error = $message }
            }
        }
        $timer.Stop()
        # File references below are entry names inside the ZIP, not deleted temp paths.
        $archivedTracks = @($tracks.ToArray() | ForEach-Object {
            [pscustomobject]@{
                Track = $_.Track; Name = $_.Name; Stats = $_.Stats; Warnings = @($_.Warnings); ProcessingSeconds = $_.ProcessingSeconds; Error = $_.Error
                Skipped = $_.Skipped; SkipReason = $_.SkipReason
                OriginalFile = if (Test-Path -LiteralPath $_.OriginalFile -PathType Leaf) {
                    [IO.Path]::GetFileName($_.OriginalFile)
                } else { $null }
                SimplifiedFile = if (Test-Path -LiteralPath $_.SimplifiedFile -PathType Leaf) {
                    [IO.Path]::GetFileName($_.SimplifiedFile)
                } else { $null }
            }
        })
        # Publish one result object; aggregate counts stay in the parent process.
        $result = [pscustomobject]@{
            File = $Relative; Destination = $ArchivePath; Archive = $ArchivePath
            RecoveryFolder = $null; AssTracks = $assCount
            OtherTracks = $otherTracks; Fonts = $fontCount
            Seconds = [Math]::Round($timer.Elapsed.TotalSeconds, 2)
            Tracks = $archivedTracks; Errors = @($errors.ToArray()); Warnings = @($warnings.ToArray())
        }
        try {
            if (-not $Destination) { throw 'No temporary result folder was created.' }
            $result | ConvertTo-Json -Depth 20 |
                Set-Content -LiteralPath (Join-Path $Destination 'result.json') -Encoding UTF8
            # Use .NET ZIP support directly, with literal paths and all files,
            # including empty logs. Fonts and intermediate working files stay out.
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            $temporaryArchive = Join-Path $work 'results.zip'
            [IO.Compression.ZipFile]::CreateFromDirectory(
                $Destination, $temporaryArchive, [IO.Compression.CompressionLevel]::Optimal, $false)
            $archiveFolder = [IO.Path]::GetDirectoryName($ArchivePath)
            [IO.Directory]::CreateDirectory($archiveFolder) | Out-Null
            # Copy the completed local ZIP under a unique staging name, then rename
            # on the destination filesystem so a partial transfer is not a final ZIP.
            $stagingArchive = Join-Path $archiveFolder ('.subtitle-zip-' + [guid]::NewGuid().ToString('N') + '.partial')
            [IO.File]::Copy($temporaryArchive, $stagingArchive)
            if (([IO.FileInfo]::new($temporaryArchive)).Length -ne ([IO.FileInfo]::new($stagingArchive)).Length) {
                throw 'Transferred ZIP size does not match the temporary archive.'
            }
            [IO.File]::Move($stagingArchive, $ArchivePath)
            $archiveSaved = $true
        } catch {
            $errors.Add("Could not save ZIP: $($_.Exception.Message). Temporary results kept at: $work")
            $result.Errors = @($errors.ToArray())
            $result.Archive = $null
            $result.RecoveryFolder = $work
            if ($stagingArchive) { Remove-Item -LiteralPath $stagingArchive -Force -ErrorAction SilentlyContinue }
            if ($Destination -and (Test-Path -LiteralPath $Destination -PathType Container)) {
                $result | ConvertTo-Json -Depth 20 |
                    Set-Content -LiteralPath (Join-Path $Destination 'result.json') -Encoding UTF8
            }
        }
        return $result
    } finally {
        $timer.Stop()
        if ($archiveSaved -and $work) {
            Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

# Update aggregate counts once per finished MKV, without rebuilding earlier results.
$summary = [pscustomobject]@{
    FilesWithErrors = 0; FilesWithoutAss = 0; OtherTracksSkipped = 0
    TracksProcessed = 0; TracksFailed = 0; TracksSkipped = 0; Original = [long]0; Remaining = [long]0
}
$totals = [ordered]@{}
$counterCoverage = [ordered]@{}
foreach ($key in $labels.Keys) {
    $totals[$key] = $null
    $counterCoverage[$key] = 0
}
$topTracks = [System.Collections.Generic.List[object]]::new()
$topConcurrentTracks = [System.Collections.Generic.List[object]]::new()
$topTimedTracks = [System.Collections.Generic.List[object]]::new()
$errorFiles = [System.Collections.Generic.List[object]]::new()
$droppedTextTracks = [System.Collections.Generic.List[object]]::new()
$colorPhaseWarnings = [System.Collections.Generic.List[object]]::new()

function Add-ResultToSummary($Item) {
    $summary.OtherTracksSkipped += [int]$Item.OtherTracks
    $summary.TracksFailed += [Math]::Max(0, [int]$Item.AssTracks - @($Item.Tracks).Count)
    if (@($Item.Errors).Count) {
        $summary.FilesWithErrors++
        $message = ([string]$Item.Errors[0] -replace '\s+', ' ').Trim()
        if ($message.Length -gt 200) { $message = $message.Substring(0, 197) + '...' }
        $errorFiles.Add([pscustomobject]@{
            File = $Item.File; Count = @($Item.Errors).Count; Message = $message
        })
    } elseif (-not $Item.AssTracks) { $summary.FilesWithoutAss++ }
    foreach ($entry in @($Item.Tracks)) {
        if ($entry.Skipped) { $summary.TracksSkipped++; continue }
        if (-not $entry.Skipped -and $null -ne $entry.ProcessingSeconds) {
            $topTimedTracks.Add([pscustomobject]@{
                File = $Item.File; Track = $entry.Track; Name = $entry.Name
                Seconds = [double]$entry.ProcessingSeconds; Failed = [bool]$entry.Error
            })
            if ($topTimedTracks.Count -gt 10) {
                $last = @($topTimedTracks.ToArray() |
                    Sort-Object @{ Expression = 'Seconds'; Descending = $true }, File, Track)[-1]
                $topTimedTracks.Remove($last) | Out-Null
            }
        }
        if ($null -eq $entry.Stats) { $summary.TracksFailed++; continue }
        $stats = ConvertTo-CurrentSubtitleStats $entry.Stats
        $entry.Stats = $stats
        $warning = Get-ScrollingDropWarning $stats
        if ($null -ne $warning) {
            $droppedTextTracks.Add([pscustomobject]@{
                File = $Item.File; Track = $entry.Track; Name = $entry.Name
                Events = $warning.Events; Limit = $warning.Limit; Blocks = $warning.Blocks
                Peak = $warning.Peak; Message = $warning.Message
            })
            Show-ScrollingDropWarning $warning ("$($Item.File) - track $($entry.Track) - $($entry.Name)")
        }
        $summary.TracksProcessed++
        $summary.Original += [long]$stats.original
        $summary.Remaining += [long]$stats.output
        Add-SubtitleCounterStats $stats $totals $counterCoverage $simplifierVersion
        $phaseWarning = Get-ColorPhaseLimitWarning $stats
        if ($phaseWarning) {
            Write-Warning ("$($Item.File) - track $($entry.Track): $phaseWarning")
            $colorPhaseWarnings.Add([pscustomobject]@{ File=$Item.File; Track=$entry.Track; Message=$phaseWarning;
                Captions=$stats.color_phase_captions_limited; Changes=$stats.color_phase_changes_removed;
                RateLimited=$stats.color_phase_rate_limited; HoldLimited=$stats.color_phase_hold_limited })
        }
        # Older simplifiers omit concurrency; do not rank missing data as zero.
        if ($null -ne $stats.max_concurrent_out) {
            $topConcurrentTracks.Add([pscustomobject]@{
                File = $Item.File; Track = $entry.Track; Name = $entry.Name
                Concurrent = [long]$stats.max_concurrent_out
            })
            if ($topConcurrentTracks.Count -gt 10) {
                $last = @($topConcurrentTracks.ToArray() |
                    Sort-Object @{ Expression = 'Concurrent'; Descending = $true }, File, Track)[-1]
                $topConcurrentTracks.Remove($last) | Out-Null
            }
        }
        # Keep only ten candidates. This sort handles at most eleven records,
        # with deterministic tie-breaking regardless of worker completion order.
        $topTracks.Add([pscustomobject]@{
            File = $Item.File; Track = $entry.Track; Name = $entry.Name
            Remaining = [long]$stats.output
        })
        if ($topTracks.Count -gt 10) {
            $last = @($topTracks.ToArray() |
                Sort-Object @{ Expression = 'Remaining'; Descending = $true }, File, Track)[-1]
            $topTracks.Remove($last) | Out-Null
        }
    }
}

function Save-Report {
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add('Cached ASS/SSA simplification test')
    $lines.Add("Input folder: $inputRoot")
    $lines.Add("Simplifier: $simplifierPath")
    $lines.Add("Simplifier SHA256: $simplifierHash")
    $lines.Add("Simplification mode: $(if ($SimplificationLevel -eq 1) { 'standard' } else { 'legacy' })")
    $limitText = if (-not $supportsScrollLimit) { 'unavailable in this simplifier' } elseif ($null -eq $ScrollConcurrencyLimit) { 'engine default' } else { [string]$ScrollConcurrencyLimit }
    $lines.Add("Scrolling-text concurrent event limit: $limitText (0 disables dropping)")
    $holdText = if ($null -eq $ColorPhaseMinHold) { 'engine default' } else { "$ColorPhaseMinHold s" }
    $intervalText = if ($null -eq $ColorPhaseChangeInterval) { 'engine default' } else { [string]$ColorPhaseChangeInterval }
    $phaseSettings = if ($supportsColorPhases) { "hold=$holdText; seconds per change=$intervalText (0 disables each limit)" } else { 'unavailable in this simplifier' }
    $lines.Add("Color phase limits: $phaseSettings")
    $lines.Add("Concurrent MKV jobs: $workerCount")
    $lines.Add("Font spacing disabled: $([bool]$NoFontSpacing)")
    if ($Encoding) { $lines.Add("Input encoding override: $Encoding") }
    $lines.Add("Status: $runState; completed $($completed.Count)/$($files.Count) MKV files")
    $lines.Add("Results folder: $runRoot")
    $lines.Add('Input is a local extraction cache; source MKVs are never opened. Counts cover successful tracks.')
    $lines.Add('Counters describe separate passes and may overlap; do not add them to calculate removal.')
    $lines.Add('Each <filename>.mkv.zip contains original/simplified subtitles, logs, stats.json and result.json.')
    $lines.Add('Track file references are ZIP entry names; combined reports are written at the end.')
    $lines.Add('Tracks marked "; Simplified by simplify_ass.py" are skipped and listed in result.json.')
    $lines.Add('')
    $lines.Add('TEXT REMOVAL WARNINGS')
    foreach ($item in @($droppedTextTracks.ToArray() | Sort-Object File, Track)) {
        $lines.Add("WARNING: $($item.Message) - $($item.File) - track $($item.Track) - $($item.Name)")
    }
    if (-not $droppedTextTracks.Count) { $lines.Add('(no scrolling-text drops reported)') }
    $lines.Add('')
    $lines.Add('COLOR PHASE LIMIT WARNINGS')
    foreach ($item in $colorPhaseWarnings) { $lines.Add("WARNING: $($item.Message) - $($item.File) - track $($item.Track)") }
    if (-not $colorPhaseWarnings.Count) { $lines.Add('(no color phase reductions reported)') }
    $lines.Add('')
    $lines.Add('SUMMARY')
    $lines.Add("MKV files found: $($files.Count)")
    $lines.Add("MKV files examined: $($completed.Count)")
    $lines.Add("Files without ASS/SSA: $($summary.FilesWithoutAss)")
    $lines.Add("Other subtitle tracks skipped: $($summary.OtherTracksSkipped)")
    $lines.Add("ASS/SSA tracks processed successfully: $($summary.TracksProcessed)")
    $lines.Add("ASS/SSA tracks failed: $($summary.TracksFailed)")
    $lines.Add("Already simplified ASS/SSA tracks skipped: $($summary.TracksSkipped)")
    $lines.Add("Files with errors: $($summary.FilesWithErrors)")
    $lines.Add("Dialogue events before: $($summary.Original)")
    $lines.Add("Dialogue events remaining: $($summary.Remaining)")
    $lines.Add('Concurrency values are maxima across individual tracks, not sums.')
    $lines.Add('Zero means every successful track reported no contribution; missing or partial counters are marked separately.')
    $lines.Add('Zero alone does not prove supersession: a matching effect may be absent or handled by an earlier pass.')
    $lines.Add('')
    foreach ($line in @(Get-SubtitleCounterReportLines $counterCatalog $totals $counterCoverage $summary.TracksProcessed)) {
        $lines.Add($line)
    }
    $lines.Add('')
    $lines.Add('TOP 10 TRACKS BY REMAINING DIALOGUE EVENTS')
    $rank = 0
    foreach ($item in @($topTracks.ToArray() |
        Sort-Object @{ Expression = 'Remaining'; Descending = $true }, File, Track)) {
        $rank++; $lines.Add("$rank. $($item.Remaining) events - $($item.File) - track $($item.Track) - $($item.Name)")
    }
    if (-not $rank) { $lines.Add('(none)') }
    $lines.Add('')
    $lines.Add('TOP 10 TRACKS BY MAXIMUM CONCURRENT EVENTS REMAINING')
    $rank = 0
    foreach ($item in @($topConcurrentTracks.ToArray() |
        Sort-Object @{ Expression = 'Concurrent'; Descending = $true }, File, Track)) {
        $rank++; $lines.Add("$rank. $($item.Concurrent) concurrent events - $($item.File) - track $($item.Track) - $($item.Name)")
    }
    if (-not $rank) { $lines.Add('(none; concurrency statistics unavailable or no successful tracks)') }
    $lines.Add('')
    $lines.Add('TOP 10 SUBTITLE TRACKS BY PROCESSING TIME')
    $lines.Add('Elapsed time per Python track, including track file I/O and lazy font measurements.')
    $lines.Add('Excludes extraction, shared font setup, Python startup and ZIP creation; parallel jobs share CPU.')
    $rank = 0
    foreach ($item in @($topTimedTracks.ToArray() |
        Sort-Object @{ Expression = 'Seconds'; Descending = $true }, File, Track)) {
        $rank++
        $displaySeconds = $item.Seconds.ToString('F3', [Globalization.CultureInfo]::InvariantCulture)
        $status = if ($item.Failed) { ' (failed)' } else { '' }
        $lines.Add("$rank. $displaySeconds seconds - $($item.File) - track $($item.Track) - $($item.Name)$status")
    }
    if (-not $rank) { $lines.Add('(none; per-track timing requires an updated simplify_ass.py or no tracks were processed)') }
    $lines.Add('')
    $lines.Add('FILES WITH ERRORS (see result.json and logs inside each ZIP; save failures name a recovery folder)')
    foreach ($item in @($errorFiles.ToArray() | Sort-Object File)) {
        $lines.Add("$($item.File) - $($item.Count) error message(s): $($item.Message)")
    }
    if (-not $errorFiles.Count) { $lines.Add('(none)') }
    $lines | Set-Content -LiteralPath $reportPath -Encoding UTF8
    [pscustomobject]@{
        Status = $runState; Started = $startedAt.ToString('o'); Updated = (Get-Date).ToString('o')
        Input = $inputRoot; Simplifier = $simplifierPath; SimplifierSHA256 = $simplifierHash; Level = $SimplificationLevel
        ScrollConcurrencyLimit = if ($supportsScrollLimit) { $ScrollConcurrencyLimit } else { $null }
        ColorPhaseWarnings = @($colorPhaseWarnings.ToArray())
        ColorPhaseMinHold = if ($supportsColorPhases) { $ColorPhaseMinHold } else { $null }
        ColorPhaseChangeInterval = if ($supportsColorPhases) { $ColorPhaseChangeInterval } else { $null }
        ScrollingDropWarnings = @($droppedTextTracks.ToArray() | Sort-Object File, Track)
        MaxParallel = $workerCount; FontSpacingDisabled = [bool]$NoFontSpacing; Encoding = $Encoding
        FilesFound = $files.Count; FilesCompleted = $completed.Count; FilesWithErrors = $summary.FilesWithErrors
        TracksProcessed = $summary.TracksProcessed; TracksFailed = $summary.TracksFailed
        TracksSkipped = $summary.TracksSkipped
        Original = $summary.Original; Remaining = $summary.Remaining; Totals = $totals
        CounterCoverage = $counterCoverage; CounterPolicy = 'active-v1'; SimplifierVersion = [string]$simplifierVersion
        Files = @($completed.ToArray() | Sort-Object File)
    } | ConvertTo-Json -Depth 25 | Set-Content -LiteralPath $jsonReportPath -Encoding UTF8
}

Write-Host "Found $($files.Count) MKV files; using up to $workerCount concurrent jobs."
Write-Host "Results: $runRoot"
$next = 0
try {
    while ($next -lt $files.Count -or $active.Count) {
        while ($next -lt $files.Count -and $active.Count -lt $workerCount) {
            $file = $files[$next]
            $relative = $file.DirectoryName.Substring($inputRoot.Length).TrimStart('\', '/')
            if (-not $relative) { $relative = [IO.Path]::GetFileName($inputRoot) }
            $destination = Join-Path $runRoot ($relative + '.zip')
            $job = Start-Job -ScriptBlock $worker -ArgumentList @(
                $file.FullName, $relative, $destination, $simplifierPath, $SimplificationLevel,
                $pythonPath, [bool]$NoFontSpacing, $Encoding, $ScrollConcurrencyLimit, $supportsScrollLimit, $ColorPhaseMinHold, $ColorPhaseChangeInterval, $supportsColorPhases)
            $active.Add([pscustomobject]@{ Job = $job; File = $relative; Destination = $destination })
            $next++
            Write-Host "Started [$next/$($files.Count)]: $relative"
        }
        foreach ($slot in @($active.ToArray())) {
            if ($slot.Job.State -notin @('Completed', 'Failed', 'Stopped')) { continue }
            $result = @(Receive-Job -Job $slot.Job -ErrorAction SilentlyContinue)
            if ($slot.Job.State -ne 'Completed' -or $result.Count -ne 1) {
                $reason = [string]$slot.Job.ChildJobs[0].JobStateInfo.Reason
                if (-not $reason) { $reason = "Worker ended with state $($slot.Job.State) and $($result.Count) results." }
                $result = @([pscustomobject]@{
                    File = $slot.File; Destination = $slot.Destination; Archive = $null
                    RecoveryFolder = $null; AssTracks = 0
                    OtherTracks = 0; Fonts = 0; Seconds = 0; Tracks = @(); Warnings = @(); Errors = @($reason)
                })
            }
            $completed.Add($result[0])
            Add-ResultToSummary $result[0]
            if (@($result[0].Errors).Count) { Write-Warning "Errors: $($slot.File). See its logs and report." }
            Write-Host "Finished [$($completed.Count)/$($files.Count)]: $($slot.File) ($($result[0].Seconds)s)"
            Remove-Job -Job $slot.Job
            $active.Remove($slot) | Out-Null
        }
        if ($active.Count) { Wait-Job -Job @($active.ToArray() | ForEach-Object { $_.Job }) -Any -Timeout 1 | Out-Null }
    }
    $runState = 'Complete'
} finally {
    foreach ($slot in @($active.ToArray())) {
        Stop-Job -Job $slot.Job -ErrorAction SilentlyContinue
        Remove-Job -Job $slot.Job -Force -ErrorAction SilentlyContinue
    }
    if ($runState -ne 'Complete') { $runState = 'Interrupted' }
    # One final write on completion, or best-effort when unwinding an interruption.
    Show-ScrollingDropSummary $droppedTextTracks.ToArray()
    if ($colorPhaseWarnings.Count) {
        $changes = ($colorPhaseWarnings | Measure-Object -Property Changes -Sum).Sum
        $captions = ($colorPhaseWarnings | Measure-Object -Property Captions -Sum).Sum
        Write-Warning "RUN SUMMARY: Removed $changes whole-caption color changes in $captions captions by color phase limits."
    }
    Save-Report
}
$fileFailures = $summary.FilesWithErrors
Write-Host "Report: $reportPath"
Write-Host "Finished $($completed.Count) MKV files in $([Math]::Round(((Get-Date) - $startedAt).TotalSeconds, 1)) seconds."
if ($fileFailures) { throw "$fileFailures MKV file(s) had errors. Successful tracks were retained. See report: $reportPath" }
