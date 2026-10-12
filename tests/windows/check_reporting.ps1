# Run on Windows PowerShell 5.1+: .\check_reporting.ps1
# Parses the wrappers and tests reporting helpers without running conversions.
$ErrorActionPreference = 'Stop'
$checks = 0
$script:captured = [System.Collections.Generic.List[object]]::new()
function Write-Host {
    param($Object, $ForegroundColor)
    $script:captured.Add([pscustomobject]@{ Text = [string]$Object; Color = $ForegroundColor })
}
foreach ($name in @('test_mkv_subtitles.ps1', 'test_subtitles_step2_test.ps1', '../../simplify_ass.ps1')) {
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
Microsoft.PowerShell.Utility\Write-Host "$checks PowerShell reporting checks passed."
