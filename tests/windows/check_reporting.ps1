# Run on Windows PowerShell 5.1+: .\check_reporting.ps1
# Parses the wrappers and tests reporting helpers without running conversions.
$ErrorActionPreference = 'Stop'
$checks = 0
$script:captured = [System.Collections.Generic.List[object]]::new()
function Write-Host {
    param($Object, $ForegroundColor)
    $script:captured.Add([pscustomobject]@{ Text = [string]$Object; Color = $ForegroundColor })
}
foreach ($name in @('test_mkv_subtitles.ps1', 'test_subtitles_step2_test.ps1')) {
    $tokens = $null; $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $PSScriptRoot $name), [ref]$tokens, [ref]$parseErrors)
    if (@($parseErrors).Count) { throw "$name syntax errors: $parseErrors" }
    $checks++
    foreach ($functionName in @('ConvertTo-CurrentSubtitleStats', 'Get-ScrollingDropWarning', 'Show-ScrollingDropWarning', 'Show-ScrollingDropSummary')) {
        $fn = $ast.Find({ param($node)
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        }, $true)
        if ($null -eq $fn) { throw "$name missing $functionName" }
        Invoke-Expression $fn.Extent.Text
    }
    foreach ($stats in @($null, [pscustomobject]@{}, [pscustomobject]@{prototype_scrolling_events_removed = 0})) {
        if ($null -ne (Get-ScrollingDropWarning $stats)) { throw 'Unexpected warning with no drops.' }
        $checks++
    }
    $warning = Get-ScrollingDropWarning ([pscustomobject]@{
        prototype_scrolling_events_removed = 1320; prototype_scrolling_concurrency_limit = 32
        prototype_scrolling_blocks_removed = 1; prototype_scrolling_peak_after_reduction = 33
    })
    if ($warning.Events -ne 1320 -or $warning.Limit -ne 32 -or $warning.Peak -ne 33) { throw 'Incorrect warning counts.' }
    $checks++
    $canonical = [pscustomobject]@{
        scrolling_events_dropped = 1320; scrolling_concurrency_limit = 32
        scrolling_blocks_dropped = 1; scrolling_peak_after_reduction = 33
    }
    $currentWarning = Get-ScrollingDropWarning $canonical
    if ($currentWarning.Events -ne $warning.Events -or $currentWarning.Message -ne $warning.Message) {
        throw 'Current and older report warnings differ.'
    }
    $checks++
    $mixed = [pscustomobject]@{
        scrolling_events_dropped = 0; prototype_scrolling_events_removed = 1320
        scrolling_concurrency_limit = 32; prototype_scrolling_concurrency_limit = 99
        stacked_text_copies_flattened = 2; aggressive_copies = 7
        future_counter = 4
    }
    $normalized = ConvertTo-CurrentSubtitleStats $mixed
    if ($null -ne (Get-ScrollingDropWarning $mixed) -or $normalized.scrolling_events_dropped -ne 0 -or
        $normalized.scrolling_concurrency_limit -ne 32 -or $normalized.stacked_text_copies_flattened -ne 2) {
        throw 'Canonical counters did not take precedence.'
    }
    $checks++
    if ($normalized.PSObject.Properties['prototype_scrolling_events_removed'] -or
        $normalized.PSObject.Properties['aggressive_copies'] -or $normalized.future_counter -ne 4 -or
        $null -eq $mixed.PSObject.Properties['prototype_scrolling_events_removed']) {
        throw 'Normalization duplicates counters, loses future data or mutates its input.'
    }
    $checks++
    $twice = ConvertTo-CurrentSubtitleStats $normalized
    if (($twice | ConvertTo-Json -Compress) -ne ($normalized | ConvertTo-Json -Compress)) {
        throw 'Normalization is not idempotent.'
    }
    $checks++
    $script:captured.Clear()
    Show-ScrollingDropWarning $warning 'example.mkv - track 4'
    if (-not @($script:captured | Where-Object { $_.Color -eq 'Red' -and $_.Text -match 'Dropped 1320 events.*limit 32' }).Count) {
        throw 'Warning was not printed in red with its counts.'
    }
    $checks++
    $script:captured.Clear()
    Show-ScrollingDropSummary -Items @()
    if ($script:captured.Count) { throw 'Empty summary produced a warning.' }
    $checks++
    Show-ScrollingDropSummary -Items @($warning, $warning)
    if (-not @($script:captured | Where-Object { $_.Text -match 'Dropped 2640 events.*limit 32' -and $_.Color -eq 'Red' }).Count) {
        throw 'Run summary did not aggregate dropped events by their real limit.'
    }
    $checks++
}
# Shared catalogs and actual wrapper aggregation/report serialization.
. (Join-Path $PSScriptRoot 'subtitle_report_helpers.ps1')
$standard = Get-SubtitleCounterCatalog 1
$legacy = Get-SubtitleCounterCatalog 2
foreach ($key in @('staggered_rows','fullwidth_merged','text_copies_removed','tiles_joined',
                  'vector_copies_removed','vector_glows_removed','covered_vectors','vector_frames_removed','excess_vectors')) {
    if ($standard.Labels.Contains($key)) { throw "Inactive standard counter: $key" }
    $checks++
}
foreach ($key in @('shared_interval_rows','shared_interval_tails','shadow_lettering_normalized','text_colors_normalized')) {
    if (-not $standard.Labels.Contains($key)) { throw "Missing live counter: $key" }
    $checks++
}
if (-not $legacy.Filters.Contains('vector_copies_removed') -or $legacy.Labels.Contains('text_colors_normalized') -or
    $legacy.Labels.Contains('staggered_rows')) { throw 'Legacy catalog includes inactive filters or loses active ones.' }
$checks++
$testFolder = Join-Path ([IO.Path]::GetTempPath()) ('subtitle-report-check-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testFolder | Out-Null
try {
    $counterBlocks = @()
    foreach ($name in @('test_mkv_subtitles.ps1','test_subtitles_step2_test.ps1')) {
        $tokens = $null; $errors = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile(
            (Join-Path $PSScriptRoot $name),[ref]$tokens,[ref]$errors)
        foreach ($functionName in @('Add-ResultToSummary','Save-Report','ConvertTo-CurrentSubtitleStats','Get-ScrollingDropWarning')) {
            $fn = $ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
                $node.Name -eq $functionName},$true)
            Invoke-Expression $fn.Extent.Text
        }
        foreach ($SimplificationLevel in @(1,2)) {
            $counterCatalog = Get-SubtitleCounterCatalog $SimplificationLevel
            $labels = $counterCatalog.Labels; $totals = [ordered]@{}; $counterCoverage = [ordered]@{}
            foreach ($key in $labels.Keys) { $totals[$key] = $null; $counterCoverage[$key] = 0 }
            $summary = [pscustomobject]@{ FilesWithErrors=0; FilesWithoutAss=0; OtherTracksSkipped=0
                TracksProcessed=0; TracksFailed=0; TracksSkipped=0; Original=[long]0; Remaining=[long]0 }
            foreach ($variable in @('topTracks','topConcurrentTracks','topTimedTracks','errorFiles','droppedTextTracks','colorPhaseWarnings','completed')) {
                Set-Variable $variable ([System.Collections.Generic.List[object]]::new())
            }
            $simplifierVersion = [version]'2026.10.12.181'
            $sample = @(
                [pscustomobject]@{original=100;output=80;max_concurrent_in=10;max_concurrent_out=2;phase_merged=0;deduped=3;text_colors_normalized=2;color_phase_captions_limited=2;color_phase_changes_removed=5;color_phase_rate_limited=1;color_phase_hold_limited=2;color_phase_min_hold=1;color_phase_change_interval=2;text_copies_removed=999;staggered_rows=999;future_counter=9},
                [pscustomobject]@{original=10;output=8;max_concurrent_in=4;max_concurrent_out=3;phase_merged=0;deduped=0},
                [pscustomobject]@{original=2;output=1;max_concurrent_in=2;max_concurrent_out=1;phase_merged=0;deduped=$null}
            )
            $tracks = @(); $index = 0
            foreach ($stats in $sample) {
                $index++; $tracks += [pscustomobject]@{Track=$index;Name='test';Stats=$stats;Warnings=@();ProcessingSeconds=1;Error=$null;Skipped=$false}
            }
            $item = [pscustomobject]@{File='example.mkv';OtherTracks=0;AssTracks=3;Tracks=$tracks;Errors=@()}
            Add-ResultToSummary $item
            $completed.Add($item)
            if ($summary.TracksProcessed -ne 3 -or $summary.Original -ne 112 -or $summary.Remaining -ne 89 -or
                $totals.max_concurrent_out -ne 3 -or $totals.deduped -ne 3 -or $counterCoverage.deduped -ne 2) {
                throw "${name}: incorrect totals, maxima or coverage"
            }
            $checks++
            if ($item.Tracks[0].Stats.future_counter -ne 9 -or $item.Tracks[0].Stats.staggered_rows -ne 999) {
                throw 'Raw statistics were lost.'
            }
            $checks++
            $reportPath=Join-Path $testFolder ($name+$SimplificationLevel+'.txt')
            $jsonReportPath=Join-Path $testFolder ($name+$SimplificationLevel+'.json')
            $inputRoot=$testFolder; $simplifierPath='simplify_ass.py'; $simplifierHash='test'
            $supportsScrollLimit=$true; $ScrollConcurrencyLimit=32; $supportsColorPhases=$true; $ColorPhaseMinHold=1; $ColorPhaseChangeInterval=2; $workerCount=1; $NoFontSpacing=$false
            $Encoding=$null; $runState='completed'; $startedAt=Get-Date; $files=@('example.mkv'); $runRoot=$testFolder
            Save-Report
            $text=Get-Content -LiteralPath $reportPath -Raw
            $json=Get-Content -LiteralPath $jsonReportPath -Raw | ConvertFrom-Json
            if ($text -notmatch 'glyph phases merged: 0\r?\n' -or
                $text -notmatch 'duplicate layers removed: 3 \(reported for 2/3 tracks; total incomplete\)' -or
                $text -match 'staggered row fragments merged|fullwidth glyph events merged' -or
                $json.CounterCoverage.phase_merged -ne 3 -or $json.Totals.phase_merged -ne 0) {
                throw 'Zero, partial, retired or JSON reporting incorrect.'
            }
            $checks++
            if ($SimplificationLevel -eq 1) {
                if ($text -match 'duplicate sign text removed|identical text strips joined|vector copies removed|excess vector details removed' -or
                    $text -notmatch 'lyric fragments merged: not reported' -or $json.Totals.lyric_merged -ne $null -or
                    $text -notmatch 'text events with normalized fill/outline colors: 2\r?\n' -or $json.CounterCoverage.text_colors_normalized -ne 3) {
                    throw 'Standard-mode missing values or sparse normalization are incorrect.'
                }
                $checks++
            } elseif ($text -notmatch 'duplicate sign text removed: 999 \(reported for 1/3 tracks; total incomplete\)') {
                throw 'Explicit legacy mode lost its active counters.'
            } else { $checks++ }
            $block=[regex]::Match($text,'(?s)ACTIVE FILTER CONTRIBUTIONS.*?(?=TOP 10 TRACKS)').Value
            $counterBlocks += [pscustomobject]@{Level=$SimplificationLevel;Text=$block}
        }
    }
    foreach ($level in @(1,2)) {
        $blocks=@($counterBlocks | Where-Object {$_.Level -eq $level})
        if ($blocks[0].Text -ne $blocks[1].Text) { throw 'Wrapper counter reports differ.' }
        $checks++
    }
    foreach ($version in @($null,[version]'2026.10.12.177',[version]'2026.10.12.181')) {
        $totals=[ordered]@{text_colors_normalized=$null};$coverage=[ordered]@{text_colors_normalized=0}
        Add-SubtitleCounterStats ([pscustomobject]@{}) $totals $coverage $version
        if ($null -ne $version -and $version -ge [version]'2026.10.12.178') {
            if ($totals.text_colors_normalized -ne 0 -or $coverage.text_colors_normalized -ne 1) { throw 'Known sparse zero not counted.' }
        } elseif ($null -ne $totals.text_colors_normalized -or $coverage.text_colors_normalized -ne 0) {
            throw 'Older/unknown converter fabricated a zero.'
        }
        $checks++
    }
    $catalog=Get-SubtitleCounterCatalog 1;$totals=[ordered]@{};$coverage=[ordered]@{}
    foreach ($key in $catalog.Labels.Keys) {$totals[$key]=$null;$coverage[$key]=0}
    $empty=@(Get-SubtitleCounterReportLines $catalog $totals $coverage 0) -join "`n"
    if ($empty -match ': 0(?:\n|$)' -or $empty -notmatch 'not reported') {throw 'Empty run fabricates filter zeros.'}
    $checks++
} finally { Remove-Item -LiteralPath $testFolder -Recurse -Force }

Microsoft.PowerShell.Utility\Write-Host "$checks PowerShell reporting checks passed."

if ($null -ne (Get-ColorPhaseLimitWarning ([pscustomobject]@{}))) { throw 'Older engine must not report a genuine zero or warning.' }
$checks++
if ($null -ne (Get-ColorPhaseLimitWarning ([pscustomobject]@{color_phase_changes_removed=0}))) { throw 'Zero color removals must not warn.' }
$checks++
$warning=Get-ColorPhaseLimitWarning ([pscustomobject]@{color_phase_changes_removed=5;color_phase_captions_limited=2;color_phase_min_hold=1;color_phase_change_interval=2;color_phase_rate_limited=1;color_phase_hold_limited=2})
if ($warning -notmatch '5 whole-caption color changes in 2 captions' -or $warning -notmatch 'rate: 1, hold: 2') { throw 'Color warning lost counters/reasons.' }
$checks++
[Console]::WriteLine("Color phase reporting checks included: $checks total.")
