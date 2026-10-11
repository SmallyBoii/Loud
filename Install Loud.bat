@echo off
rem Double-click: runs install.ps1 in a window that stays open so you can read the result. No administrator rights are needed.
rem PowerShell is started from its own system folder (not looked up through PATH).
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -NoExit -File "%~dp0install.ps1"
