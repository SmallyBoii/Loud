# Changelog

## 1.4.0

- **A proper installer and release zip.** The release is now `Loud-<version>.zip` with `Install Loud.bat` (double-click, no administrator rights), `install.ps1`, `uninstall.ps1`, the license, third-party notices and a short README.txt, next to `app\Loud.exe`. The installer copies the program to `%LOCALAPPDATA%\Programs\Loud`, checks the copy against the original by SHA-256, adds a Start-menu shortcut and a Settings > Apps entry, and asks whether Loud should start with Windows. Until now the release was a bare `Loud.exe`, which gave a first-time user no way to remove it cleanly.
- **A checksum for every release.** `Loud-<version>.zip.sha256` is published next to the zip, with an LF line ending so `sha256sum -c` works as well as `Get-FileHash`. (An earlier version of the workflow wrote Windows line endings, which Linux tools could not read, and the checksum was dropped for a while.)
- **The uninstaller only removes what it can prove is Loud.** It refuses a folder without `Loud.exe`, a drive root or a top-level folder, removes the start-with-Windows value only if it points at this install, and asks before deleting your settings (`-KeepData` keeps them).
- **The workflow follows least privilege.** Read-only token, every action pinned to a full commit hash, `persist-credentials: false`, tests (including an install and uninstall round trip into a scratch folder) before packaging, and a separate release job that only uploads what the build job made. Before, one job built and published.
- **`build.ps1` and `tools/package.ps1`** replace `build.bat`.
- Added `SECURITY.md`, `THIRD-PARTY-NOTICES.md` with the license texts of what `Loud.exe` contains, a Privacy and a Limits section in the README, and real screenshots.

## 1.3.0

- **The boost slider jumps to where you click.** Before, clicking the bar did nothing and only dragging the handle worked.

## 1.2.0

- **A landscape window.** The window is two columns instead of one tall column, so it fits small and scaled screens. If the screen is still too short, a scrollbar appears.

## 1.1.0

- **Loud mode.** An optional switch that rounds off peaks before the limiter, for more volume at the cost of sound quality. It is off by default and the window says so. The clean limiter cannot go past the speakers' maximum level, so on songs that are already loud it can change very little beyond about +6 dB.
- **Start Loud when Windows starts** (packaged exe only), through the per-user Run key.

## 1.0.0

First public release.
