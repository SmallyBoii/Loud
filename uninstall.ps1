<#
 Loud uninstaller. Run from the install folder (or from the extracted release folder):  .\uninstall.ps1
 Removes: the program folder, the Start-menu shortcut, the Settings > Apps entry and the start-with-Windows value.
 Asks whether to delete your settings and log in %APPDATA%\Loud (-KeepData keeps them, -Yes deletes them without asking).
 Nothing else on the PC is touched. Spotify's own output setting is not changed: if Spotify is still sent to a silent output,
 set it back to Default in Windows Settings > System > Sound > Volume mixer.

 Switches:  -Yes   -KeepData   -InstallDir <folder>   -NoShortcut and -NoUninstallEntry (used by the tests)
#>
[CmdletBinding()]
param(
    [string]$InstallDir,
    [switch]$Yes,
    [switch]$KeepData,
    [switch]$NoShortcut,
    [switch]$NoUninstallEntry
)
$ErrorActionPreference = 'Stop'

function Step([string]$Text) { Write-Host "  $Text" }

$localApp = [Environment]::GetFolderPath('LocalApplicationData')
$appData = [Environment]::GetFolderPath('ApplicationData')
$programs = [Environment]::GetFolderPath('Programs')
if (-not $InstallDir) {
    # Prefer the folder this script runs from when it is an install folder, else the default location.
    $here = $PSScriptRoot
    if ($here -and (Test-Path -LiteralPath (Join-Path $here 'Loud.exe'))) { $InstallDir = $here }
    else { $InstallDir = Join-Path $localApp 'Programs\Loud' }
}
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
if ([IO.Path]::GetPathRoot($InstallDir) -eq $InstallDir -or $InstallDir.TrimEnd('\').Split('\').Count -lt 3) {
    throw "Refusing to remove '$InstallDir': that is a drive root or a top-level folder."
}
$targetExe = Join-Path $InstallDir 'Loud.exe'
if ((Test-Path -LiteralPath $InstallDir) -and -not (Test-Path -LiteralPath $targetExe)) {
    throw "'$InstallDir' does not contain Loud.exe, so it does not look like a Loud install folder. Nothing was removed."
}

Write-Host ''
Write-Host 'Loud uninstaller' -ForegroundColor Cyan
Write-Host "  Install folder: $InstallDir"

$deleteData = $false
if (-not $KeepData) {
    if ($Yes) { $deleteData = $true }
    else {
        while ($true) {
            $answer = (Read-Host "Also delete your Loud settings and log in $appData\Loud? [y/N]").Trim().ToLowerInvariant()
            if ($answer -eq '' -or $answer -in @('n', 'no')) { break }
            if ($answer -in @('y', 'yes')) { $deleteData = $true; break }
        }
    }
}

# Close the running copy from this install folder (only that one).
foreach ($p in @(Get-Process -Name 'Loud' -ErrorAction SilentlyContinue)) {
    $path = $null
    try { $path = $p.Path } catch { }
    if ($path -and ([string]::Equals($path, $targetExe, 'OrdinalIgnoreCase'))) {
        Step "Closing the running Loud ($($p.Id))"
        $p.CloseMainWindow() | Out-Null
        if (-not $p.WaitForExit(4000)) { Stop-Process -Id $p.Id -Force; $p.WaitForExit(4000) | Out-Null }
    }
}

if (-not $NoShortcut) {
    $link = Join-Path $programs 'Loud.lnk'
    if (Test-Path -LiteralPath $link) { Remove-Item -LiteralPath $link -Force; Step 'Removed the Start-menu shortcut' }
}

$run = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$value = $null
try { $value = (Get-ItemProperty -Path $run -Name 'Loud' -ErrorAction Stop).Loud } catch { }
# Only remove the start-with-Windows value if it points at this install.
if ($value -and ([string]::Equals($value.Trim('"'), $targetExe, 'OrdinalIgnoreCase'))) {
    Remove-ItemProperty -Path $run -Name 'Loud' -Force
    Step 'Removed start-with-Windows'
}

if (-not $NoUninstallEntry) {
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Loud'
    if (Test-Path -Path $key) { Remove-Item -Path $key -Recurse -Force; Step 'Removed the Settings > Apps entry' }
}

if (Test-Path -LiteralPath $InstallDir) {
    # A junction or symbolic link inside the folder is removed as a link; Remove-Item does not enter it.
    Remove-Item -LiteralPath $InstallDir -Recurse -Force
    Step 'Removed the program folder'
}

if ($deleteData) {
    $data = Join-Path $appData 'Loud'
    if (Test-Path -LiteralPath $data) { Remove-Item -LiteralPath $data -Recurse -Force; Step 'Deleted your settings and log' }
} else {
    Step "Kept your settings and log in $appData\Loud"
}

Write-Host ''
Write-Host 'Done. If Spotify is still sent to a silent output, set it back to Default in Windows Volume mixer.' -ForegroundColor Green
