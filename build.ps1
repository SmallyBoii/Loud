<#
 Builds Loud and publishes a single Loud.exe to .\dist (PyInstaller, no Python needed on the target PC).
   .\build.ps1                      uses .venv if it exists, else the python on PATH
   .\build.ps1 -Python python       uses the python on PATH (what CI does)
#>
[CmdletBinding()]
param(
    [string]$Python,
    [string]$Output = (Join-Path $PSScriptRoot 'dist')
)
$ErrorActionPreference = 'Stop'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'

# Windows PowerShell 5.1 turns anything a native tool writes to stderr (PyInstaller logs its progress there) into an error.
# Run the tools with errors non-terminating and judge them by their exit code instead.
function Invoke-Native([scriptblock]$Command, [string]$What) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Command 2>&1 | ForEach-Object { "$_" } | Write-Host } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)" }
}

if (-not $Python) {
    $venv = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    $Python = if (Test-Path $venv) { $venv } else { 'python' }
}

Invoke-Native { & $Python -m pip install --quiet -r (Join-Path $PSScriptRoot 'requirements.txt') pyinstaller } 'Installing the build requirements'

if (Test-Path $Output) { Remove-Item $Output -Recurse -Force }
$work = Join-Path $PSScriptRoot 'build'
Invoke-Native {
    & $Python -m PyInstaller --noconfirm --onefile --windowed --name Loud --distpath $Output --workpath $work --specpath $work `
        --paths $PSScriptRoot --exclude-module matplotlib --exclude-module scipy --exclude-module pandas (Join-Path $PSScriptRoot 'launch.py')
} 'PyInstaller'
Write-Host "Published to $Output"
