"""Where is Spotify's sound going? Reads Windows audio sessions and the process list; changes nothing."""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field

from . import wasapi

PROCESS = "spotify.exe"


@dataclass
class SpotifyState:
    running: bool = False
    playing_on: str = None                      # endpoint id with an active Spotify session
    seen_on: set = field(default_factory=set)   # endpoints with any Spotify session, idle included


class _ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]


def _spotify_running():
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return False
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel32.Process32FirstW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == PROCESS:
                return True
            ok = kernel32.Process32NextW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
        return False
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(snapshot))


def check(endpoint_ids):
    state = SpotifyState(running=_spotify_running())
    for ident in endpoint_ids:
        for name, session_state in wasapi.audio_sessions(ident):
            if name.lower() == PROCESS:
                state.seen_on.add(ident)
                if session_state == wasapi.SESSION_ACTIVE:
                    state.playing_on = ident
    return state


def advice(state, source_id, output_id, names):
    """(level, message) telling the user whether Spotify will reach Loud. level: ok | warn | info."""
    source, output = names.get(source_id, "Loud's input"), names.get(output_id, "your headphones")
    fix = (f"In Windows Volume mixer, set Spotify's output device to {source} "
           "(newer Spotify versions also have an Output device setting in Settings > Playback).")
    if not state.running:
        return "info", "Spotify isn't running. Open it and play something."
    if state.playing_on == source_id:
        return "ok", f"Spotify is playing into {source}, which Loud boosts."
    if state.playing_on == output_id:
        return "warn", f"Spotify is playing straight to {output}, so Loud can't boost it. {fix}"
    if state.playing_on:
        return "warn", f"Spotify is playing on {names.get(state.playing_on, 'another device')}, not Loud's input. {fix}"
    if source_id in state.seen_on:
        return "ok", f"Spotify is routed to {source}. Play a song to hear the boost."
    if state.seen_on:
        return "warn", f"Spotify isn't routed to Loud's input. {fix}"
    return "info", f"Spotify is open but hasn't played yet. Start a song and I'll check it's routed to {source}."

