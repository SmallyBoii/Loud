"""Diagnostics: `python -m loud.probe` lists playback devices and what each supports. Plays nothing."""
import time

from . import wasapi


def main():
    endpoints = wasapi.list_render_endpoints()
    default_id = wasapi.default_render_endpoint_id()
    print("Playback devices:")
    for ident, name in endpoints:
        vol = wasapi.get_endpoint_volume(ident)
        vol_text = "n/a" if vol is None else f"{vol * 100:.0f}%"
        print(f"  {'*' if ident == default_id else ' '} {name}   (Windows volume {vol_text})")
        print(f"      {ident}")
        support = wasapi.exclusive_support(ident)
        rates = sorted({r for r, _, _ in support})
        print(f"      exclusive mode: {', '.join(f'{r} Hz' for r in rates) if rates else 'not available'}")
        states = {wasapi.SESSION_ACTIVE: "PLAYING", wasapi.SESSION_INACTIVE: "idle", wasapi.SESSION_EXPIRED: "expired"}
        sessions = [(n, s) for n, s in wasapi.audio_sessions(ident) if n != "pid 0"]
        if sessions:
            print("      apps with audio sessions: " + ", ".join(f"{n} [{states.get(s, s)}]" for n, s in sessions))
    print("  (* = Windows default output)\n")

    for ident, name in endpoints:
        try:
            cap = wasapi.LoopbackCapture(ident)
        except wasapi.WasapiError as e:
            print(f"loopback {name}: {e}")
            continue
        start, frames = time.time(), 0
        while time.time() - start < 1.0:
            frames += len(cap.read())
            time.sleep(0.005)
        print(f"loopback {name}: {cap.rate} Hz, {cap.channels} ch, {cap.bits}-bit "
              f"{'float' if cap.is_float else 'int'}, captured {frames} frames in 1 s")
        cap.close()


if __name__ == "__main__":
    main()
