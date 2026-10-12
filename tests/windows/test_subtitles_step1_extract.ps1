# Extract reusable ASS/SSA subtitles and fonts. Windows PowerShell 5.1+.
# Example: .\extract_mkv_test_data.ps1 -InputFolder '\\NAS\Videos' -OutputFolder 'D:\SubtitleCache'
# Completed caches are skipped on subsequent runs unless -Refresh is supplied.
param(
    [string] $InputFolder,
    [Parameter(Mandatory=$true)] [string] $OutputFolder,
    [string] $MkvToolNixFolder,
    [switch] $Refresh
)
$ErrorActionPreference = 'Stop'
if (-not $InputFolder) { $InputFolder = (Get-Location).Path }
function Resolve-MkvTool([string] $Name) {
    if ($MkvToolNixFolder) {
        foreach ($suffix in @('.exe', '')) {
            $candidate = Join-Path $MkvToolNixFolder ($Name + $suffix)
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                return (Resolve-Path -LiteralPath $candidate).Path
            }
        }
        throw "Cannot find $Name in $MkvToolNixFolder"
    }
    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    if ($env:ProgramFiles) {
        $candidate = Join-Path $env:ProgramFiles ("MKVToolNix\" + $Name + '.exe')
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    throw "Cannot find $Name. Install MKVToolNix or pass -MkvToolNixFolder."
}

function Normalize-Folder([string] $Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -eq [IO.Path]::GetPathRoot($full)) { return $full }
    return $full.TrimEnd('\', '/')
}


$inputRoot = Normalize-Folder (Resolve-Path -LiteralPath $InputFolder).Path
$outputRoot = Normalize-Folder $OutputFolder
if ($outputRoot -ieq $inputRoot) { throw 'OutputFolder must differ from InputFolder.' }
$mkvmerge = Resolve-MkvTool 'mkvmerge'
$mkvextract = Resolve-MkvTool 'mkvextract'
[IO.Directory]::CreateDirectory($outputRoot) | Out-Null
$outputPrefix = $outputRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
$files = @(Get-ChildItem -LiteralPath $inputRoot -Filter '*.mkv' -File -Recurse |
    Where-Object { -not $_.FullName.StartsWith($outputPrefix, [StringComparison]::OrdinalIgnoreCase) } |
    Sort-Object FullName)
$failed = 0; $done = 0; $skipped = 0
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




foreach ($file in $files) {
    $relative = $file.FullName.Substring($inputRoot.Length).TrimStart('\', '/')
    $target = Join-Path $outputRoot $relative
    if (Test-Path -LiteralPath $target) {
        $manifestPath = Join-Path $target 'manifest.json'
        if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
            $failed++; Write-Warning "Destination already exists without a cache manifest: $target"; continue
        }
        try {
            $existing = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($existing.Format -ne 'subtitle-test-cache' -or $existing.Version -ne 1) {
                throw 'Unsupported cache manifest; destination left untouched.'
            }
            $complete = $true
            foreach ($record in @($existing.Tracks) + @($existing.Fonts)) {
                if (-not $record.File -or [IO.Path]::IsPathRooted([string]$record.File) -or
                    @($record.File -split '[/\\]' | Where-Object { $_ -eq '..' }).Count -or
                    -not (Test-Path -LiteralPath (Join-Path $target $record.File) -PathType Leaf)) { $complete=$false }
            }
            if ($complete -and -not $Refresh -and $existing.SourceSize -eq $file.Length -and
                ([datetime]$existing.SourceModified).ToUniversalTime().Ticks -eq $file.LastWriteTimeUtc.Ticks) {
                $skipped++; Write-Host "Cached: $relative"; continue
            }
        } catch {
            $failed++; Write-Warning "$relative : $($_.Exception.Message)"; continue
        }
    }
    $work = Join-Path ([IO.Path]::GetTempPath()) ('subtitle-extract-' + [guid]::NewGuid().ToString('N'))
    $Destination = Join-Path $work 'cache'
    $stage = $null; $backup = $null; $saved = $false
    try {
        [IO.Directory]::CreateDirectory($Destination) | Out-Null
        $code = Invoke-LoggedTool $mkvmerge @('--output-charset','UTF-8','-J',$file.FullName) 'identify'
        if ($code -notin @(0,1)) { throw "Identification failed (exit code $code)." }
        $info = Get-Content -LiteralPath (Join-Path $Destination 'identify.stdout.log') -Raw -Encoding UTF8 | ConvertFrom-Json
        $tracks = @($info.tracks | Where-Object { $_.type -eq 'subtitles' -and $_.properties.codec_id -in @('S_TEXT/ASS','S_TEXT/SSA') })
        $fonts = [Collections.Generic.List[object]]::new()
        [IO.Directory]::CreateDirectory((Join-Path $Destination 'fonts')) | Out-Null
        foreach ($a in @($info.attachments)) {
            if ($null -eq $a) { continue }
            $ext = [IO.Path]::GetExtension([string]$a.file_name).ToLowerInvariant()
            $mime = ([string]$a.content_type).ToLowerInvariant()
            if ($ext -notin @('.ttf','.otf','.ttc','.otc')) {
                if ($mime -notin @('application/x-truetype-font','application/vnd.ms-opentype',
                    'application/x-font-ttf','application/x-font-opentype','font/ttf','font/otf',
                    'font/collection','application/font-sfnt')) { continue }
                $ext = if ($mime -eq 'font/collection') { '.ttc' } else { '.ttf' }
            }
            $fonts.Add([pscustomobject]@{ Id=[int]$a.id; Name=[string]$a.file_name; File="fonts/font-$($a.id)$ext" })
        }
        $records = @($tracks | ForEach-Object {
            $ext = if ($_.properties.codec_id -eq 'S_TEXT/SSA') { '.ssa' } else { '.ass' }
            [pscustomobject]@{ Track=[int]$_.id; Name=[string]$_.properties.track_name; File="track-$($_.id)$ext" }
        })
        # One invocation and one scan: all requested subtitle tracks and attachments.
        # Paths are relative to the cache folder, avoiding Windows drive-colon issues.
        $arguments = @('--output-charset','UTF-8',$file.FullName)
        if ($records.Count) {
            $arguments += 'tracks'
            $arguments += @($records | ForEach-Object { "$($_.Track):$($_.File)" })
        }
        if ($fonts.Count) {
            $arguments += 'attachments'
            $arguments += @($fonts | ForEach-Object { "$($_.Id):$($_.File)" })
        }
        if ($records.Count -or $fonts.Count) {
            $code = Invoke-LoggedTool $mkvextract $arguments 'extract'
            if ($code -notin @(0,1)) { throw "Extraction failed (exit code $code)." }
        }
        foreach ($record in @($records) + @($fonts.ToArray())) {
            if (-not (Test-Path -LiteralPath (Join-Path $Destination $record.File) -PathType Leaf)) {
                throw "Extracted file missing: $($record.File)"
            }
        }
        [pscustomobject]@{
            Format='subtitle-test-cache'; Version=1; RelativeFile=$relative
            SourceFile=$file.FullName; SourceSize=$file.Length; SourceModified=$file.LastWriteTimeUtc.ToString('o')
            Extracted=(Get-Date).ToString('o'); Tracks=@($records); Fonts=@($fonts.ToArray())
            OtherTracks=@($info.tracks | Where-Object { $_.type -eq 'subtitles' -and $_.properties.codec_id -notin @('S_TEXT/ASS','S_TEXT/SSA') }).Count
        } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $Destination 'manifest.json') -Encoding UTF8
        $parent = [IO.Path]::GetDirectoryName($target)
        [IO.Directory]::CreateDirectory($parent) | Out-Null
        $stage = Join-Path $parent ('.subtitle-cache-' + [guid]::NewGuid().ToString('N'))
        Copy-Item -LiteralPath $Destination -Destination $stage -Recurse
        if (Test-Path -LiteralPath $target) {
            # Never remove an unrelated existing directory.
            if (-not (Test-Path -LiteralPath (Join-Path $target 'manifest.json') -PathType Leaf)) {
                throw "Destination already exists without a cache manifest: $target"
            }
            $backup = Join-Path $parent ('.subtitle-old-' + [guid]::NewGuid().ToString('N'))
            [IO.Directory]::Move($target,$backup)
        }
        try { [IO.Directory]::Move($stage,$target) }
        catch {
            if ($backup) { [IO.Directory]::Move($backup,$target); $backup=$null }
            throw
        }
        $saved=$true
        if ($backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
        $done++; Write-Host "Extracted: $relative ($($records.Count) tracks, $($fonts.Count) fonts)"
    } catch {
        $failed++; Write-Warning "$relative : $($_.Exception.Message) Working data retained: $work"
    } finally {
        if ($stage -and (Test-Path -LiteralPath $stage)) { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
        if ($saved) { Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue }
    }
}
Write-Host "Extracted: $done; already cached: $skipped; failed: $failed. Cache: $outputRoot"
if ($failed) { throw "$failed MKV file(s) could not be cached. See warnings above." }
