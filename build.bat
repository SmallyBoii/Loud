@echo off
rem Builds dist\Loud.exe, a single file that runs on any Windows 10/11 PC with no Python installed.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install --quiet pyinstaller
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed --name Loud --distpath dist ^
  --workpath build --specpath build --paths . --exclude-module matplotlib --exclude-module scipy ^
  --exclude-module pandas launch.py
