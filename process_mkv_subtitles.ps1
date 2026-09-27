# Requires Windows PowerShell 5.1+ or PowerShell 7, Python 3 and MKVToolNix.
# Put simplify_ass_lyrics_v2.py beside this script, or supply -Simplifier.
param(
    [string] $InputFolder,
    [string] $OutputFolder,
    [string] $Simplifier,
    [string] $Python = 'python',
    [string] $MkvToolNixFolder,
    [switch] $Recurse
)

$ErrorActionPreference = 'Stop'
if (-not $InputFolder) { $InputFolder = (Get-Location).Path }
if (-not $Simplifier) {
    $Simplifier = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'simplify_ass_lyrics_v2.py'
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
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

$files = @(Get-ChildItem -LiteralPath $inputRoot -Filter '*.mkv' -File -Recurse:$Recurse |
    Where-Object { -not $_.FullName.StartsWith($outputRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) })
if (-not $files.Count) { Write-Host 'No MKV files found.'; return }

$failures = 0
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

        $replacements = @()
        foreach ($track in $assTracks) {
            $ext = if ($track.properties.codec_id -eq 'S_TEXT/SSA') { '.ssa' } else { '.ass' }
            $extracted = Join-Path $work ("track-$($track.id)" + $ext)
            & $mkvextract $file.FullName tracks ("$($track.id):$extracted")
            Check-Exit "extract track $($track.id)"
            if (-not (Test-Path -LiteralPath $extracted -PathType Leaf)) { throw "Track $($track.id) was not extracted." }

            & $pythonPath $simplifierPath $extracted
            Check-Exit "simplify track $($track.id)"
            $simple = Join-Path $work ("track-$($track.id).simple" + $ext)
            if (-not (Test-Path -LiteralPath $simple -PathType Leaf)) { throw "Missing simplified track: $simple" }
            $replacements += [pscustomobject]@{ Original = $track; File = $simple }
        }

        $ids = ($assTracks | ForEach-Object { $_.id }) -join ','
        $mergeArgs = [System.Collections.Generic.List[string]]::new()
        $mergeArgs.Add('-o'); $mergeArgs.Add($partial)
        if (@($info.tracks | Where-Object { $_.type -eq 'subtitles' }).Count -eq $assTracks.Count) {
            $mergeArgs.Add('--no-subtitles')
        } else {
            $mergeArgs.Add('--subtitle-tracks'); $mergeArgs.Add('!' + $ids)
        }
        $mergeArgs.Add($file.FullName)

        foreach ($replacement in $replacements) {
            $properties = $replacement.Original.properties
            $language = if ($properties.language_ietf) { $properties.language_ietf } else { $properties.language }
            if ($language) { $mergeArgs.Add('--language'); $mergeArgs.Add('0:' + $language) }
            if ($properties.track_name) { $mergeArgs.Add('--track-name'); $mergeArgs.Add('0:' + $properties.track_name) }
            if ($null -ne $properties.default_track) { $mergeArgs.Add('--default-track-flag'); $mergeArgs.Add('0:' + (Flag $properties.default_track)) }
            if ($null -ne $properties.forced_track) { $mergeArgs.Add('--forced-display-flag'); $mergeArgs.Add('0:' + (Flag $properties.forced_track)) }
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
            if ($index -ge 0) { $order += "$(($index + 1)):0" }
            else { $order += "0:$($track.id)" }
        }
        $mergeArgs.Add('--track-order'); $mergeArgs.Add(($order -join ','))
        & $mkvmerge @mergeArgs
        Check-Exit 'mkvmerge remux'
        if (-not (Test-Path -LiteralPath $partial -PathType Leaf)) { throw 'Remux did not create an MKV.' }
        $outputInfo = ((& $mkvmerge -J $partial) -join "`n" | ConvertFrom-Json)
        Check-Exit 'output validation'
        if (@($outputInfo.tracks).Count -ne @($info.tracks).Count) { throw 'Output track count differs from input.' }
        Move-Item -LiteralPath $partial -Destination $destination -ErrorAction Stop
        Write-Host "  Saved: $destination ($($assTracks.Count) ASS/SSA track(s) simplified)"
    } catch {
        $failures++
        Write-Warning "Failed: $($file.FullName): $_"
        if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
    } finally {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
}
if ($failures) { throw "$failures file(s) failed. See warnings above." }
