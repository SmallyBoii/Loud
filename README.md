# Loud

**Make Spotify louder than Windows' 100% limit, without turning up anything else.**

Spotify too quiet on your laptop, even with every volume slider maxed? Loud boosts Spotify only, by up to +24 dB,
and keeps the sound clean with a limiter. Games, Discord, your browser and every other app keep playing at their
normal volume on the same speakers or headphones.

- Boost Spotify up to +24 dB, with a look-ahead limiter so peaks don't clip
- Other apps are untouched and play alongside it
- Global hotkeys to change the boost from any window
- One small file, no installer, nothing runs in the background after you close it
- Free and open source, runs entirely on your PC (no network use, no accounts, no telemetry)

**Requirements:** Windows 10 or 11, and Spotify for Windows. A second audio output is needed. If your PC only has
one, the free VB-Cable virtual device provides it (see [Set up](#set-up)).

## Download

Get **Loud.exe** from the [latest release](../../releases/latest) and put it anywhere, such as your Desktop.
No installation and no Python needed.

Windows may show a blue "Windows protected your PC" box the first time, because the file isn't code-signed.
Click **More info**, then **Run anyway**. The source is in this repo if you'd rather read it or
[build it yourself](#for-developers).

## How it works

Windows can only send an app's sound to an audio device that exists. Loud uses that: Spotify is sent to a second,
silent output, and Loud listens there, boosts the sound, and plays it on your real speakers or headphones.

```
Spotify --(Windows per-app routing)--> silent output --loopback--> Loud
Loud:   gain (up to +24 dB) -> look-ahead limiter (-0.3 dBFS) -> your speakers/headphones
Other apps --------------------------------------------------> your speakers/headphones
```

The limiter holds peaks just under full scale, so extra boost raises the average loudness instead of clipping.

## Set up

Do this once.

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

### If your PC has two outputs (for example speakers plus a monitor with built-in audio)

You don't need VB-Cable. In the Windows Volume mixer, send Spotify to the output you don't listen on (the
monitor). Open Loud, check that it lists your speakers or headphones as the output and the other device as its
input, and press **Start**.

Spotify is silent while it's sent to the silent output and Loud isn't running. That's expected.

## Using it

- Press **Start**. The Spotify panel turns green once Loud hears Spotify playing.
- Raise **Boost** slowly. It fades in over 1.5 seconds each time Loud starts. +6 dB is about twice as loud,
  +12 dB about four times.
- Hotkeys that work from any window:
  - `Ctrl+Alt+PageUp` / `Ctrl+Alt+PageDown`: boost up or down 1 dB
  - `Ctrl+Alt+0`: back to 0 dB
- After the first Start, Loud starts itself when you open it. Press **Stop** and it won't, until you press Start
  again.
- The **Output** and **Limiter** bars show how loud the result is and how much the limiter is holding peaks back.

## Tips

- In Spotify > Settings > Audio quality, turn **audio normalization off** (or set the volume level to Loud).
  Otherwise Spotify turns loud songs down before Loud can boost them.
- Leave Spotify's **Exclusive Mode** off. It takes over the audio device and blocks Loud from hearing it.
- Keep the Windows volume on your speakers or headphones at 100%. Loud shows a button to set it if it's lower.
- Headphones can't play louder than the hardware's full-scale output. Past that point, Loud raises the average
  level by compressing peaks, so very high boost sounds denser.
- If the volume drifts back down after a moment, tick **Bypass Windows and audio-driver effects (exclusive mode)**.
  That skips all Windows sound effects (Equalizer APO, Realtek and similar), but every other app is silent on those
  speakers while Loud runs.
- Loud adds roughly 30 ms of delay, which is fine for music but not for lip-syncing video.
- **Very loud sound can damage your hearing and your speakers. Raise the boost slowly.**

## To undo it

Close Loud, then in the Windows Volume mixer set Spotify's output back to **Default** (or choose your normal
speakers in Spotify's own output setting).

## Troubleshooting

| Problem | What to do |
|---|---|
| No sound from Spotify | Loud isn't running, or Spotify isn't sent to the silent output. Press Start and check the Spotify panel in Loud. |
| Spotify panel is orange | Spotify is playing somewhere else. Follow the fix it shows. Spotify must be playing for it to appear in the Volume mixer. |
| "Only one audio output found" | Install VB-Cable (see above), restart, then press **Rescan devices**. |
| "Stopped: the audio device went away" | The device Loud was listening on disappeared (monitor off, cable removed). Turn it back on and press Start. |
| Boost seems to do nothing | Turn off Spotify's audio normalization, and make sure Windows volume on your speakers is 100%. |

Errors are written to `%APPDATA%\Loud\loud.log`. Running `python -m loud.probe` lists your playback devices, what
each supports, and which apps are using them. It plays nothing.

## For developers

Needs Windows 10/11 and Python 3. The only dependency is NumPy; audio goes through WASAPI via `ctypes`.

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m loud                          # run from source (or Loud.bat)
.venv\Scripts\python -m unittest discover -s tests    # run the tests
.venv\Scripts\python -m loud.probe                    # list playback devices
build.bat                                             # build dist\Loud.exe with PyInstaller
```

Code layout: `loud/wasapi.py` (audio devices, loopback capture, output), `loud/engine.py` (real-time loop),
`loud/dsp.py` (gain and limiter), `loud/devices.py` (device selection), `loud/spotify.py` (detects where Spotify's
sound is going), `loud/app.py` (window).

## Disclaimer

Loud is an independent project. It is not affiliated with or endorsed by Spotify or VB-Audio. It doesn't modify
Spotify: it only processes the audio Windows is already playing. It's provided as is, with no warranty.
