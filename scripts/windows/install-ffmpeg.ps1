<#
.SYNOPSIS
  Downloads a portable FFmpeg build into tools\ffmpeg for IDK Clips.

.DESCRIPTION
  Source: https://www.gyan.dev/ffmpeg/builds/ (the Windows builds linked from ffmpeg.org).
  The download is verified against the SHA-256 checksum published next to it.
  Nothing is installed system-wide and PATH is not modified: IDK Clips finds
  tools\ffmpeg\bin automatically.

.PARAMETER Force
  Re-download even if tools\ffmpeg\bin\ffmpeg.exe already exists.
#>
[CmdletBinding()]
param([switch]$Force)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is far faster without the progress UI
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$dest = Join-Path $root 'tools\ffmpeg'
$ffmpegExe = Join-Path $dest 'bin\ffmpeg.exe'

if ((Test-Path -LiteralPath $ffmpegExe) -and -not $Force) {
    Write-Host "FFmpeg is already installed in $dest (use -Force to reinstall)."
    & $ffmpegExe -hide_banner -version | Select-Object -First 1
    exit 0
}

$zipUrl = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
$work = Join-Path $root 'tools\.ffmpeg-download'
$zip = Join-Path $work 'ffmpeg-release-essentials.zip'
$shaFile = "$zip.sha256"

New-Item -ItemType Directory -Force -Path $work | Out-Null
try {
    Write-Host "Downloading $zipUrl ..."
    Invoke-WebRequest -Uri $zipUrl -OutFile $zip -UseBasicParsing
    Invoke-WebRequest -Uri "$zipUrl.sha256" -OutFile $shaFile -UseBasicParsing

    $expected = ((Get-Content -LiteralPath $shaFile -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
    $actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($expected -notmatch '^[0-9a-f]{64}$') { throw "The published checksum could not be read." }
    if ($actual -ne $expected) { throw "Checksum mismatch: expected $expected but got $actual. The download was rejected." }
    $sizeMb = [math]::Round((Get-Item -LiteralPath $zip).Length / 1MB, 1)
    Write-Host "Checksum verified (SHA-256 $actual, $sizeMb MB)."

    $extract = Join-Path $work 'extract'
    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
    $inner = Get-ChildItem -LiteralPath $extract -Directory | Select-Object -First 1
    if (-not $inner -or -not (Test-Path -LiteralPath (Join-Path $inner.FullName 'bin\ffmpeg.exe'))) {
        throw "The archive did not contain bin\ffmpeg.exe."
    }
    if (Test-Path -LiteralPath $dest) {
        $backup = "$dest.previous"
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
        Move-Item -LiteralPath $dest -Destination $backup
        Write-Host "Previous FFmpeg kept in $backup"
    }
    Move-Item -LiteralPath $inner.FullName -Destination $dest
}
finally {
    if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Recurse -Force }
}

Write-Host "Installed to $dest"
& $ffmpegExe -hide_banner -version | Select-Object -First 1
