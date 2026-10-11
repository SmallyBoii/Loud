<#
 Loud installer. Double-click "Install Loud.bat", or run:  .\install.ps1     (no administrator rights are needed)

 What it does (and nothing else):
   1. Copies Loud.exe (from .\app in the release zip, or .\dist after build.ps1) to %LOCALAPPDATA%\Programs\Loud, together with
      uninstall.ps1, the license and the third-party notices. Only your own account's folders are touched.
   2. Adds a Start-menu shortcut "Loud" and an entry in Settings > Apps > Installed apps (so Windows can uninstall it).
   3. Asks whether Loud should start when you sign in to Windows (a value in your own HKCU Run key; you can change it later in
      Loud itself or by running uninstall.ps1).
   4. Starts Loud.
 uninstall.ps1 reverses all of it.

 Nothing is downloaded and nothing needs administrator rights. Your settings and log live in %APPDATA%\Loud and are created by
 the program itself, not by this installer.

 Switches:  -Yes (accept the defaults, no questions)   -StartAtLogon (start with Windows, no question)   -NoStart (do not launch it)
            -Source <folder with Loud.exe>   -InstallDir <folder>
            -NoShortcut and -NoUninstallEntry skip the Start-menu shortcut and the Apps entry (used by the tests).
#>
[CmdletBinding()]
param(
    [string]$Source,
    [string]$InstallDir,
    [switch]$StartAtLogon,
    [switch]$NoStart,
    [switch]$Yes,
    [switch]$NoShortcut,
    [switch]$NoUninstallEntry
)
$ErrorActionPreference = 'Stop'

function Ask([string]$Question, [bool]$Default) {
    if ($Yes) { return $Default }
    $hint = if ($Default) { '[Y/n]' } else { '[y/N]' }
    while ($true) {
        $answer = (Read-Host "$Question $hint").Trim().ToLowerInvariant()
        if ($answer -eq '') { return $Default }
        if ($answer -in @('y', 'yes')) { return $true }
        if ($answer -in @('n', 'no')) { return $false }
    }
}

function Step([string]$Text) { Write-Host "  $Text" }

# Locations come from Windows' own records, not from environment variables.
$localApp = [Environment]::GetFolderPath('LocalApplicationData')
$programs = [Environment]::GetFolderPath('Programs')
if (-not $InstallDir) { $InstallDir = Join-Path $localApp 'Programs\Loud' }
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
if ([IO.Path]::GetPathRoot($InstallDir) -eq $InstallDir -or $InstallDir.TrimEnd('\').Split('\').Count -lt 3) {
    throw "Refusing to install into '$InstallDir': that is a drive root or a top-level folder."
}

# Find the program to install: -Source, else .\app (release zip), else .\dist (after build.ps1).
if (-not $Source) {
    foreach ($candidate in @((Join-Path $PSScriptRoot 'app'), (Join-Path $PSScriptRoot 'dist'))) {
        if (Test-Path -LiteralPath (Join-Path $candidate 'Loud.exe')) { $Source = $candidate; break }
    }
}
if (-not $Source -or -not (Test-Path -LiteralPath (Join-Path $Source 'Loud.exe'))) {
    throw "Loud.exe was not found. Run this script from the extracted release folder (it has an 'app' folder), or build it first with build.ps1."
}
$Source = [IO.Path]::GetFullPath($Source)

$version = ''
$versionFile = Join-Path $PSScriptRoot 'version.txt'
if (Test-Path -LiteralPath $versionFile) { $version = (Get-Content -LiteralPath $versionFile -TotalCount 1).Trim() }

Write-Host ''
Write-Host "Loud $version installer" -ForegroundColor Cyan
Write-Host "  From: $Source"
Write-Host "  To:   $InstallDir"
Write-Host ''

$startAtLogon = [bool]$StartAtLogon
if (-not $StartAtLogon) { $startAtLogon = Ask 'Start Loud when you sign in to Windows?' $false }

# 1. Stop a running copy from the install folder (only that one), then copy.
$targetExe = Join-Path $InstallDir 'Loud.exe'
foreach ($p in @(Get-Process -Name 'Loud' -ErrorAction SilentlyContinue)) {
    $path = $null
    try { $path = $p.Path } catch { }
    if ($path -and ([string]::Equals($path, $targetExe, 'OrdinalIgnoreCase'))) {
        Step "Closing the running Loud ($($p.Id))"
        $p.CloseMainWindow() | Out-Null
        if (-not $p.WaitForExit(4000)) { Stop-Process -Id $p.Id -Force; $p.WaitForExit(4000) | Out-Null }
    }
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -LiteralPath (Join-Path $Source 'Loud.exe') -Destination $targetExe -Force
$expected = (Get-FileHash -LiteralPath (Join-Path $Source 'Loud.exe') -Algorithm SHA256).Hash
$actual = (Get-FileHash -LiteralPath $targetExe -Algorithm SHA256).Hash
if ($expected -ne $actual) { throw 'The copied Loud.exe does not match the original. Nothing else was changed.' }
Step "Copied Loud.exe (SHA-256 $($actual.Substring(0, 16).ToLowerInvariant())...)"

foreach ($name in @('uninstall.ps1', 'LICENSE', 'THIRD-PARTY-NOTICES.md')) {
    $from = Join-Path $PSScriptRoot $name
    if (Test-Path -LiteralPath $from) { Copy-Item -LiteralPath $from -Destination (Join-Path $InstallDir $name) -Force }
}
$licensesFrom = Join-Path $PSScriptRoot 'licenses'
if (Test-Path -LiteralPath $licensesFrom) { Copy-Item -LiteralPath $licensesFrom -Destination $InstallDir -Recurse -Force }
if ($version) { Set-Content -LiteralPath (Join-Path $InstallDir 'version.txt') -Value $version -Encoding ASCII }

# 2. Start-menu shortcut and the Settings > Apps entry.
if (-not $NoShortcut) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut((Join-Path $programs 'Loud.lnk'))
    $link.TargetPath = $targetExe
    $link.WorkingDirectory = $InstallDir
    $link.Description = 'Make Spotify louder than the Windows 100% limit'
    $link.Save()
    Step 'Added the Start-menu shortcut'
}
if (-not $NoUninstallEntry) {
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Loud'
    New-Item -Path $key -Force | Out-Null
    $psExe = Join-Path ([Environment]::SystemDirectory) 'WindowsPowerShell\v1.0\powershell.exe'
    $uninstallCmd = '"{0}" -NoProfile -ExecutionPolicy Bypass -File "{1}"' -f $psExe, (Join-Path $InstallDir 'uninstall.ps1')
    Set-ItemProperty -Path $key -Name DisplayName -Value 'Loud'
    Set-ItemProperty -Path $key -Name Publisher -Value 'SmallyBoii'
    Set-ItemProperty -Path $key -Name InstallLocation -Value $InstallDir
    Set-ItemProperty -Path $key -Name DisplayIcon -Value $targetExe
    Set-ItemProperty -Path $key -Name UninstallString -Value $uninstallCmd
    Set-ItemProperty -Path $key -Name NoModify -Value 1 -Type DWord
    Set-ItemProperty -Path $key -Name NoRepair -Value 1 -Type DWord
    if ($version) { Set-ItemProperty -Path $key -Name DisplayVersion -Value $version }
    Step 'Added Loud to Settings > Apps > Installed apps'
}

# 3. Start with Windows (same registry value Loud itself uses for its "Start Loud when Windows starts" checkbox).
if ($startAtLogon) {
    $run = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    New-Item -Path $run -Force | Out-Null
    Set-ItemProperty -Path $run -Name 'Loud' -Value ('"{0}"' -f $targetExe)
    Step 'Loud will start when you sign in'
}

# 4. Start it.
if (-not $NoStart) {
    Start-Process -FilePath $targetExe -WorkingDirectory $InstallDir
    Step 'Started Loud'
}

Write-Host ''
Write-Host 'Done. To remove Loud, use Settings > Apps, or run uninstall.ps1 from the install folder.' -ForegroundColor Green
Write-Host 'First time? Loud needs Spotify sent to a second, silent output. The README explains the one-time setup.'
