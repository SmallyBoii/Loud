<#
 Packs the release zip from .\dist (run build.ps1 first):
   .\tools\package.ps1 -Version 1.4.0
 Writes release\Loud-<version>.zip and release\Loud-<version>.zip.sha256 (one line: "<sha256>  <file name>", LF line ending).
 Inside the zip: app\Loud.exe, Install Loud.bat, install.ps1, uninstall.ps1, LICENSE, THIRD-PARTY-NOTICES.md, CHANGELOG.md,
 licenses\, version.txt and a short README.txt.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Version,
    [string]$Dist,
    [string]$Out
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if (-not $Dist) { $Dist = Join-Path $root 'dist' }
if (-not $Out) { $Out = Join-Path $root 'release' }
if ($Version -notmatch '^[0-9A-Za-z][0-9A-Za-z.\-]*$') { throw "Unsafe version string '$Version'" }
$exe = Join-Path $Dist 'Loud.exe'
if (-not (Test-Path $exe)) { throw "$exe not found. Run build.ps1 first." }

$name = "Loud-$Version"
$stage = Join-Path $Out $name
if (Test-Path $Out) { Remove-Item $Out -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'app') | Out-Null
Copy-Item $exe (Join-Path $stage 'app\Loud.exe')
foreach ($f in @('Install Loud.bat', 'install.ps1', 'uninstall.ps1', 'LICENSE', 'THIRD-PARTY-NOTICES.md', 'CHANGELOG.md')) {
    Copy-Item (Join-Path $root $f) (Join-Path $stage $f)
}
Copy-Item (Join-Path $root 'licenses') (Join-Path $stage 'licenses') -Recurse
Set-Content (Join-Path $stage 'version.txt') $Version -Encoding ASCII

$readme = @"
Loud $Version

Install:   double-click "Install Loud.bat" (no administrator rights needed). Answer the question in the window (Enter accepts the default).
Uninstall: Settings > Apps > Installed apps > Loud, or run .\uninstall.ps1 from the install folder.
More:      the README on the project page explains what Loud does, the one-time setup (Spotify needs to be sent to a second, silent
           output; a PC with one output can use the free VB-Cable), what it keeps private, and its limits.

Loud is released under the MIT license (LICENSE). Bundled libraries: THIRD-PARTY-NOTICES.md.
"@
Set-Content (Join-Path $stage 'README.txt') ($readme -replace "`r`n", "`n") -Encoding ASCII -NoNewline

$zip = Join-Path $Out "$name.zip"
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($stage, $zip, [IO.Compression.CompressionLevel]::Optimal, $true)
Remove-Item $stage -Recurse -Force

$hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText("$zip.sha256", "$hash  $name.zip`n")
Write-Host "Created $zip"
Write-Host "SHA-256 $hash"
