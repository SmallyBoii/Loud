# Loud

Makes **Spotify louder than Windows' 100% limit**, and only Spotify. Everything else (Discord, games, browser)
keeps playing at its normal volume on the same speakers or headphones.

## Download

Get **Loud.exe** from the [Releases page](../../releases/latest) and put it anywhere (the Desktop is fine). No
installer and no Python needed.

Windows may show a blue "Windows protected your PC" box the first time, because the file isn't code-signed.
Click **More info**, then **Run anyway**.

## Set up (once)

Windows can only send an app's sound to an audio device that exists, so Loud listens on a **second, silent
output**. Spotify is sent there, Loud boosts it, and plays it on your real speakers or headphones.

### If your PC has only one sound output (most laptops)

1. Install the free **VB-Cable** virtual audio device from <https://vb-audio.com/Cable/>. Unzip it, run
   `VBCABLE_Setup_x64.exe` as administrator, then **restart your PC**.
2. Keep your real speakers or headphones as the Windows default output. Don't make the cable the default.
3. Make Spotify play to the cable. Either:
   - in Spotify, **Settings > Playback**, choose **CABLE Input** as the output device (if your version has that
     setting), or
   - in Windows, **Settings > System > Sound > Volume mixer**, find **Spotify** (it has to be playing) and set its
     output to **CABLE Input**.
4. Open **Loud.exe** and press **Start**.

Spotify is silent while it's sent to the cable and Loud isn't running. That's expected.

### If your PC has two outputs (for example speakers plus a monitor with speakers)

You don't need VB-Cable. In the Windows Volume mixer, send Spotify to the output you don't listen on (the
monitor), open Loud, check that it lists your speakers/headphones as the output and the monitor as its input,
and press **Start**.

## Using it

- Press **Start**. The Spotify panel turns green once Loud hears Spotify playing.
- Raise **Boost** slowly. It fades in over 1.5 seconds each time Loud starts. +6 dB is about twice as loud,
  +12 dB about four times.
- Hotkeys that work from any window:
  - `Ctrl+Alt+PageUp` / `Ctrl+Alt+PageDown`: boost up or down 1 dB
  - `Ctrl+Alt+0`: back to 0 dB
- After the first Start, Loud starts itself when you open it. Press **Stop** and it won't, until you press Start
  again.
- The **Output** and **Limiter** bars show how loud the result is and how much the limiter is holding peaks
  back. It keeps the sound from clipping, so extra boost makes the average level louder instead of distorted.

## Tips

- In Spotify > Settings > Audio quality, turn **audio normalization off** (or set the volume level to Loud).
  Otherwise Spotify turns loud songs down before Loud can boost them.
- Leave Spotify's **Exclusive Mode** off. It takes over the audio device and blocks Loud from hearing it.
- Keep the Windows volume on your speakers or headphones at 100%. Loud shows a button to set it if it's lower.
- If the volume keeps drifting back down, tick **Bypass Windows and Realtek effects (exclusive mode)**. That
  skips all Windows sound effects, but every other app is silent on those speakers while Loud runs.
- Very loud sound can damage your hearing and your speakers. Raise the boost slowly.

## To undo it

Close Loud, then in the Windows Volume mixer set Spotify's output back to **Default** (or choose your normal
speakers in Spotify's own output setting).

## Troubleshooting

| Problem | What to do |
|---|---|
| No sound from Spotify | Loud isn't running, or Spotify isn't sent to the cable/monitor. Press Start, and check the Spotify panel in Loud. |
| Spotify panel is orange | Spotify is playing somewhere else. Follow the fix it shows. Spotify must be playing for it to appear in the Volume mixer. |
| "Only one audio output found" | Install VB-Cable (see above), restart, then press **Rescan devices**. |
| "Stopped: the audio device went away" | The device Loud was listening on disappeared (monitor off, cable removed). Turn it back on and press Start. |
| Sound is delayed | Loud adds about 30 ms, which is fine for music but not for lip-syncing video. |

Errors are written to `%APPDATA%\Loud\loud.log`.

## For developers

Needs Windows 10/11 and Python 3.

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m loud                          # run from source (or Loud.bat)
.venv\Scripts\python -m unittest discover -s tests    # tests
.venv\Scripts\python -m loud.probe                    # lists playback devices; plays nothing
build.bat                                             # builds dist\Loud.exe
```

How it works:

```
Spotify --(Windows per-app routing)--> silent output --loopback--> Loud
Loud: gain (up to +24 dB) -> look-ahead limiter (-0.3 dBFS) -> real speakers/headphones
Other apps ------------------------------------------------------> real speakers/headphones
```
