# Run with Windows PowerShell 5.1+: .\check_test_settings.ps1
# Validates actual wrapper parameter binding and worker argument construction.
# Does not run simplify_ass.py or access any media.
$ErrorActionPreference = 'Stop'
$checks = 0
$names = @('ScrollConcurrencyLimit', 'ColorPhaseMinHold', 'ColorPhaseChangeInterval')
$switches = @{
    ScrollConcurrencyLimit = '--scroll-concurrency-limit'
    ColorPhaseMinHold = '--color-phase-min-hold'
    ColorPhaseChangeInterval = '--color-phase-change-interval'
}
function Assert-Arguments([string[]] $Arguments, [hashtable] $Expected) {
    foreach ($name in $names) {
        $index = [Array]::IndexOf($Arguments, $switches[$name])
        if ($Expected.ContainsKey($name)) {
            $value = $Expected[$name].ToString([Globalization.CultureInfo]::InvariantCulture)
            if ($index -lt 0 -or $Arguments[$index + 1] -cne $value) {
                throw "Missing or incorrect argument: $name"
            }
        } elseif ($index -ge 0) {
            throw "Omitted setting was forwarded: $name"
        }
        $script:checks++
    }
}
$previousCulture = [Threading.Thread]::CurrentThread.CurrentCulture
try {
    [Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::GetCultureInfo('de-DE')
    foreach ($file in @('test_mkv_subtitles.ps1', 'test_subtitles_step2_test.ps1')) {
        $path = Join-Path $PSScriptRoot $file
        $tokens = $null; $errors = $null
        $ast = [Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
        if (@($errors).Count) { throw "$file syntax errors: $errors" }
        foreach ($name in $names) {
            $parameter = $ast.ParamBlock.Parameters | Where-Object { $_.Name.VariablePath.UserPath -eq $name }
            if ($null -eq $parameter -or $null -ne $parameter.DefaultValue) {
                throw "$file still defines a default for $name"
            }
            $checks++
        }
        $parameterBody = @'

[pscustomobject]@{
    ScrollConcurrencyLimit = $ScrollConcurrencyLimit
    ColorPhaseMinHold = $ColorPhaseMinHold
    ColorPhaseChangeInterval = $ColorPhaseChangeInterval
}
'@
        $parameterProbe = [scriptblock]::Create($ast.ParamBlock.Extent.Text + "`n" + $parameterBody)
        $source = [IO.File]::ReadAllText($path)
        $start = $source.IndexOf('$arguments = @($SimplifierPath,')
        $end = $source.IndexOf('if ($Level -eq 1 -and -not $DisableSpacing)', $start)
        if ($start -lt 0 -or $end -lt $start) { throw "$file missing worker arguments" }
        $argumentBody = @'
param($ScrollLimit, $SupportsScrollLimit, $PhaseHold, $PhaseInterval, $SupportsColorPhases)
$SimplifierPath = 'engine.py'; $Level = 1; $statsPath = 'stats.json'
'@
        $argumentProbe = [scriptblock]::Create($argumentBody + "`n" + $source.Substring($start, $end - $start) + "`n[pscustomobject]@{ Arguments = @(`$arguments) }")
        foreach ($parameters in @(@{},
                @{ ScrollConcurrencyLimit = 0; ColorPhaseMinHold = 0; ColorPhaseChangeInterval = 0 },
                @{ ColorPhaseMinHold = 0.5 }, @{ ColorPhaseChangeInterval = 2 }, @{ ScrollConcurrencyLimit = 16 })) {
            $bound = & $parameterProbe @parameters
            foreach ($name in $names) {
                if (-not $parameters.ContainsKey($name) -and $null -ne $bound.$name) {
                    throw "$file converts missing $name into a value"
                }
                $checks++
            }
            $built = & $argumentProbe $bound.ScrollConcurrencyLimit $true $bound.ColorPhaseMinHold $bound.ColorPhaseChangeInterval $true
            Assert-Arguments $built.Arguments $parameters
        }
        # Exercise serialization across the same Start-Job boundary as the wrappers.
        foreach ($parameters in @(@{}, @{ ScrollConcurrencyLimit = 0; ColorPhaseMinHold = 0.5; ColorPhaseChangeInterval = 0 })) {
            $bound = & $parameterProbe @parameters
            $job = Start-Job -ScriptBlock $argumentProbe -ArgumentList @(
                $bound.ScrollConcurrencyLimit, $true, $bound.ColorPhaseMinHold, $bound.ColorPhaseChangeInterval, $true)
            try {
                $built = Receive-Job -Job $job -Wait -ErrorAction Stop
                if ($job.State -ne 'Completed') { throw "$file argument probe job failed" }
                Assert-Arguments $built.Arguments $parameters
            } finally {
                Remove-Job -Job $job -Force
            }
        }
        foreach ($parameters in @(@{ ScrollConcurrencyLimit = -1 }, @{ ColorPhaseMinHold = -0.5 },
                                  @{ ColorPhaseChangeInterval = [double]::NaN },
                                  @{ ColorPhaseMinHold = [double]::PositiveInfinity })) {
            $rejected = $false
            try { $null = & $parameterProbe @parameters } catch { $rejected = $true }
            if (-not $rejected) { throw "$file accepted invalid settings" }
            $checks++
        }
    }
} finally {
    [Threading.Thread]::CurrentThread.CurrentCulture = $previousCulture
}
Write-Host "Passed $checks wrapper setting checks."
