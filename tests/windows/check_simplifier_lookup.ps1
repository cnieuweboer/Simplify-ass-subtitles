# Run on Windows PowerShell 5.1+: .\check_simplifier_lookup.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'subtitle_report_helpers.ps1')
$root = Join-Path ([IO.Path]::GetTempPath()) ('subtitle-lookup-' + [guid]::NewGuid().ToString('N'))
$previousPath = $env:PATH
$checks = 0
function New-TestFile([string] $Path) {
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path))
    [IO.File]::WriteAllText($Path, '# test fixture')
    return $Path
}
function Assert-Resolved([string] $Actual, [string] $Expected) {
    if ($Actual -ne (Resolve-Path -LiteralPath $Expected).Path) { throw "Unexpected simplifier: $Actual; expected $Expected" }
    $script:checks++
}
try {
    $scripts = Join-Path $root 'checkout/tests/windows'
    [void][IO.Directory]::CreateDirectory($scripts)
    $local = New-TestFile (Join-Path $scripts 'simplify_ass.py')
    $repository = New-TestFile (Join-Path $root 'checkout/simplify_ass.py')
    $pathFolder = Join-Path $root 'direct path with spaces'
    $onPath = New-TestFile (Join-Path $pathFolder 'simplify_ass.py')
    $explicit = New-TestFile (Join-Path $root 'explicit.py')
    $env:PATH = $pathFolder
    Assert-Resolved (Resolve-SubtitleSimplifier $scripts $explicit) $explicit
    Assert-Resolved (Resolve-SubtitleSimplifier $scripts '') $local
    Remove-Item -LiteralPath $local
    Assert-Resolved (Resolve-SubtitleSimplifier $scripts '') $repository
    Remove-Item -LiteralPath $repository
    Assert-Resolved (Resolve-SubtitleSimplifier $scripts '') $onPath
    $env:PATH = '"' + $pathFolder + '"'
    Assert-Resolved (Resolve-SubtitleSimplifier $scripts '') $onPath
    $bin = Join-Path $root 'custom installed tools/bin'
    $installed = New-TestFile (Join-Path $root 'custom installed tools/simplify-ass/simplify_ass.py')
    foreach ($name in @('subtitle_tools.cmd', 'simplify_subtitles.cmd', 'subtitle_tools_update.cmd')) {
        $launcher = New-TestFile (Join-Path $bin $name)
        $env:PATH = $bin
        Assert-Resolved (Resolve-SubtitleSimplifier $scripts '') $installed
        Remove-Item -LiteralPath $launcher
    }
    $env:PATH = (Join-Path $root 'missing path') + [IO.Path]::PathSeparator + $pathFolder
    Assert-Resolved (Resolve-SubtitleSimplifier $scripts '') $onPath
    $threw = $false
    try { [void](Resolve-SubtitleSimplifier $scripts (Join-Path $root 'missing.py')) } catch { $threw = $true }
    if (-not $threw) { throw 'An explicit missing script silently fell back.' }
    $checks++
    $env:PATH = ''
    $threw = $false
    try { [void](Resolve-SubtitleSimplifier $scripts '') } catch { $threw = $true }
    if (-not $threw) { throw 'Missing simplifier did not report an error.' }
    $checks++
    Write-Host "$checks simplifier lookup checks passed."
} finally {
    $env:PATH = $previousPath
    if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
