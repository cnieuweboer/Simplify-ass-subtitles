# Shared aggregate reporting for both test wrappers (Windows PowerShell 5.1+).
# Raw per-track statistics remain untouched, including legacy and unknown keys.
function Get-SubtitleCounterCatalog([int] $Level = 1) {
    $filters = [ordered]@{
        deduped = 'duplicate layers removed'
        phase_merged = 'glyph phases merged'
        merged = 'frame pieces merged'
        static_merged = 'identical timed copies merged'
        dropped = 'drawings/effects dropped'
    }
    $diagnostics = [ordered]@{
        max_concurrent_in = 'maximum concurrent events before (across tracks)'
        max_concurrent_out = 'maximum concurrent events remaining (across tracks)'
        vector_output = 'vector events retained'
    }
    if ($Level -eq 1) {
        $active = [ordered]@{
            lyric_merged = 'lyric fragments merged'
            overlap_removed = 'overlapping effects removed'
            full_copies_removed = 'full lyric copies removed'
            stacked_text_copies_flattened = 'stacked text copies flattened'
            text_effect_sequences_frozen = 'text effect sequences frozen'
            progressive_rows = 'progressive row fragments merged'
            overlaid_letters = 'overlaid letters removed'
            covered_fragments = 'covered fragments removed'
            masked_decorations = 'masked decorations removed'
            cue_overlaps_trimmed = 'lyric cue overlaps trimmed'
            vector_text_recovered = 'vector captions recovered'
            shared_interval_rows = 'shared-interval rows joined'
            drawing_strips_collapsed = 'drawing strips collapsed'
            drawing_duplicates_removed = 'duplicate supporting drawings removed'
            drawing_fade_frames_removed = 'drawing fade frames removed'
            unsupported_drawings_excluded = 'unsupported drawings excluded from candidate pool'
            drawing_contours_simplified = 'drawing contours simplified'
            drawing_scale_exits_frozen = 'drawing scale exits held static'
            drawing_move_entrances_frozen = 'drawing move entrances held static'
            drawing_edge_slivers_detached = 'drawing edge slivers detached'
            composite_backdrops_built = 'composite caption backdrops built'
            scrolling_events_dropped = 'scrolling-text events dropped'
            scrolling_blocks_dropped = 'scrolling-text blocks dropped'
            masked_foregrounds_restored = 'masked text foregrounds restored'
            shadow_offsets_repaired = 'text shadow positions repaired'
            drawing_events_capped = 'supporting drawings removed by vector budget'
            font_textures_removed = 'font textures removed'
            shadow_lettering_normalized = 'shadow lettering normalized'
            text_colors_normalized = 'text events with normalized fill/outline colors'
        }
        $output = [ordered]@{
            shared_interval_tails = 'shared-interval tails retained'
            drawing_candidates = 'supporting drawing candidates'
            backdrops_retained = 'caption backdrops retained'
            supporting_shapes_retained = 'supporting shapes retained'
            fullscreen_backgrounds_retained = 'fullscreen backgrounds retained'
            adjacent_shapes_retained = 'adjacent supporting shapes retained'
            unmeasured_backdrops_retained = 'unmeasured caption backdrops retained'
            scrolling_blocks_detected = 'scrolling-text blocks detected'
            scrolling_blocks_retained = 'scrolling-text blocks retained'
            scrolling_peak_after_reduction = 'maximum scrolling-text concurrency after reduction (across tracks)'
        }
        foreach ($key in $active.Keys) { $filters[$key] = $active[$key] }
        foreach ($key in $output.Keys) { $diagnostics[$key] = $output[$key] }
    } else {
        $legacy = [ordered]@{
            text_copies_removed = 'duplicate sign text removed'
            tiles_joined = 'identical text strips joined'
            vector_copies_removed = 'vector copies removed'
            vector_glows_removed = 'covered contours removed'
            covered_vectors = 'fully covered drawings removed'
            vector_frames_removed = 'drawing animation frames removed'
            excess_vectors = 'excess vector details removed'
        }
        foreach ($key in $legacy.Keys) { $filters[$key] = $legacy[$key] }
    }
    $labels = [ordered]@{}
    foreach ($group in @($filters, $diagnostics)) {
        foreach ($key in $group.Keys) { $labels[$key] = $group[$key] }
    }
    return [pscustomobject]@{ Filters = $filters; Diagnostics = $diagnostics; Labels = $labels }
}

function Get-SubtitleSimplifierVersion([string] $PythonPath, [string] $SimplifierPath) {
    try {
        $output = @(& $PythonPath $SimplifierPath --version 2>$null)
        $parsed = $null
        if ($LASTEXITCODE -eq 0 -and $output.Count -eq 1 -and
            [version]::TryParse(([string]$output[0]).Trim(), [ref]$parsed)) { return $parsed }
    } catch { }
    return $null
}

function Add-SubtitleCounterStats($Stats, $Totals, $Coverage, [version] $ConverterVersion = $null) {
    foreach ($key in @($Totals.Keys)) {
        $property = $Stats.PSObject.Properties[$key]
        if ($null -ne $property -and $null -ne $property.Value) {
            $value = [long]$property.Value
        } elseif ($null -eq $property -and $key -eq 'text_colors_normalized' -and
                  $null -ne $ConverterVersion -and $ConverterVersion -ge [version]'2026.10.12.178') {
            # v178+ emits this sparse counter only when the pass changes text.
            $value = [long]0
        } else { continue }
        if ($null -eq $Totals[$key]) { $Totals[$key] = [long]0 }
        if ($key -in @('max_concurrent_in', 'max_concurrent_out', 'scrolling_peak_after_reduction')) {
            $Totals[$key] = [Math]::Max([long]$Totals[$key], $value)
        } else { $Totals[$key] += $value }
        $Coverage[$key]++
    }
}

function Get-SubtitleCounterReportLines($Catalog, $Totals, $Coverage, [int] $TracksProcessed) {
    foreach ($section in @(
        [pscustomobject]@{ Title = 'ACTIVE FILTER CONTRIBUTIONS'; Labels = $Catalog.Filters },
        [pscustomobject]@{ Title = 'OUTPUT AND DIAGNOSTIC COUNTERS'; Labels = $Catalog.Diagnostics }
    )) {
        $section.Title
        foreach ($key in $section.Labels.Keys) {
            $count = [int]$Coverage[$key]
            if ($count -eq 0) {
                $value = 'not reported'
            } elseif ($count -lt $TracksProcessed) {
                $value = "$($Totals[$key]) (reported for $count/$TracksProcessed tracks; total incomplete)"
            } else { $value = [string]$Totals[$key] }
            "$($section.Labels[$key]): $value"
        }
        ''
    }
}
