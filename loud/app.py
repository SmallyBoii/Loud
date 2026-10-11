"""Loud: desktop window."""
import ctypes
import json
import logging
import math
import os
import queue
import threading
import tkinter as tk
from ctypes import byref, wintypes
from tkinter import ttk

from . import devices as device_pick, spotify, startup, wasapi
from .config import DATA_DIR, LOG_PATH, SETTINGS_PATH
from .dsp import MAX_GAIN_DB, MIN_GAIN_DB
from .engine import Engine

log = logging.getLogger("loud")

BG, PANEL, FG, MUTED = "#14161b", "#1d2027", "#e8e9ec", "#8b90a0"
ACCENT, GOOD, WARN, BAD = "#ff7a2f", "#38c172", "#f2b84b", "#ef5b5b"
LEVEL_COLORS = {"ok": GOOD, "warn": WARN, "info": MUTED}

MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, WM_HOTKEY = 0x1, 0x2, 0x4000, 0x0312
# Ctrl+Alt + PageUp / PageDown / 0
HOTKEYS = {1: (0x21, "up"), 2: (0x22, "down"), 3: (0x30, "reset")}


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(data):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def start_hotkeys(events):
    """Global Ctrl+Alt+PageUp/PageDown/0 so the level can be changed or reset from any window."""
    def loop():
        user32 = ctypes.windll.user32
        for ident, (vk, _) in HOTKEYS.items():
            user32.RegisterHotKey(None, ident, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, vk)
        msg = wintypes.MSG()
        while user32.GetMessageW(byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam in HOTKEYS:
                events.put(HOTKEYS[msg.wParam][1])
    threading.Thread(target=loop, name="loud-hotkeys", daemon=True).start()


class Meter(tk.Canvas):
    def __init__(self, parent, color):
        super().__init__(parent, height=10, bg=PANEL, highlightthickness=0)
        self._color = color
        self._level = 0.0

    def show(self, fraction, color=None):
        self._level = max(fraction, self._level * 0.85)
        self.delete("all")
        width = self.winfo_width()
        self.create_rectangle(0, 0, width * min(self._level, 1.0), 10, fill=color or self._color, width=0)


class App:
    def __init__(self, root):
        self.root = root
        self.engine = None
        self.events = queue.Queue()
        self.settings = load_settings()
        self.devices = []
        self._ticks = 0

        root.title("Loud")
        root.configure(bg=BG)
        root.resizable(False, False)
        root.report_callback_exception = self._on_error
        self._style()
        self._build()
        self._refresh_devices()
        start_hotkeys(self.events)
        root.protocol("WM_DELETE_WINDOW", self._close)
        self._tick()
        if self.settings.get("autostart"):
            root.after(600, self._start)

    # ---- layout -------------------------------------------------------------------------------

    def _style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG, font=("Segoe UI", 10))
        style.configure("Panel.TLabel", background=PANEL, foreground=FG, font=("Segoe UI", 10))
        style.configure("Head.TLabel", background=PANEL, foreground=FG, font=("Segoe UI Semibold", 10))
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Big.TLabel", background=PANEL, foreground=ACCENT, font=("Segoe UI Semibold", 26))
        style.configure("Title.TLabel", background=BG, foreground=FG, font=("Segoe UI Semibold", 20))
        style.configure("Sub.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 10))
        style.configure("TCombobox", fieldbackground=BG, background=BG, foreground=FG, arrowcolor=FG,
                        bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL)
        style.map("TCombobox", fieldbackground=[("readonly", BG)], foreground=[("readonly", FG)],
                  selectbackground=[("readonly", BG)], selectforeground=[("readonly", FG)])
        style.configure("TCheckbutton", background=PANEL, foreground=FG, font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", PANEL)])
        style.configure("TButton", background=PANEL, foreground=FG, bordercolor=PANEL, padding=6,
                        font=("Segoe UI", 10))
        style.map("TButton", background=[("active", "#2a2e38")])
        style.configure("Go.TButton", background=ACCENT, foreground="#1a1005", font=("Segoe UI Semibold", 12),
                        padding=10)
        style.map("Go.TButton", background=[("active", "#ff9152")])
        style.configure("Stop.TButton", background=BAD, foreground="#1a0a0a", font=("Segoe UI Semibold", 12),
                        padding=10)
        style.map("Stop.TButton", background=[("active", "#f47878")])
        style.configure("Horizontal.TScale", background=PANEL, troughcolor=BG, bordercolor=PANEL)
        self.root.option_add("*TCombobox*Listbox.background", PANEL)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

    def _build(self):
        outer = ttk.Frame(self.root, padding=18)
        outer.grid()
        ttk.Label(outer, text="Loud", style="Title.TLabel").grid(sticky="w")
        ttk.Label(outer, text="Spotify, louder than Windows' 100%", style="Sub.TLabel").grid(sticky="w", pady=(0, 12))

        sp = ttk.Frame(outer, style="Panel.TFrame", padding=14)
        sp.grid(sticky="ew", pady=(0, 10))
        ttk.Label(sp, text="Spotify", style="Head.TLabel").grid(sticky="w")
        self.spotify_msg = ttk.Label(sp, text="Checking...", style="Muted.TLabel", wraplength=410, justify="left")
        self.spotify_msg.grid(sticky="w", pady=(4, 0))
        ttk.Button(sp, text="Open Volume mixer", command=lambda: os.startfile("ms-settings:apps-volume")
                   ).grid(sticky="w", pady=(8, 0))

        devices = ttk.Frame(outer, style="Panel.TFrame", padding=14)
        devices.grid(sticky="ew", pady=(0, 10))
        ttk.Label(devices, text="Your headphones or speakers (where the boosted sound plays)",
                  style="Panel.TLabel").grid(sticky="w")
        self.output = ttk.Combobox(devices, state="readonly", width=52)
        self.output.grid(sticky="ew", pady=(2, 8))
        ttk.Label(devices, text="Loud's input (the silent output Spotify is sent to)", style="Panel.TLabel"
                  ).grid(sticky="w")
        self.source = ttk.Combobox(devices, state="readonly", width=52)
        self.source.grid(sticky="ew", pady=(2, 8))
        self.setup = ttk.Frame(devices, style="Panel.TFrame")
        self.setup.grid(sticky="ew", pady=(0, 8))
        ttk.Label(self.setup, style="Panel.TLabel", wraplength=410, justify="left", foreground=WARN,
                  text="Only one audio output found. Loud needs a second, silent one to listen on. Install the "
                       "free VB-Cable virtual audio device (one time, then restart your PC), then pick "
                       "\"CABLE Input\" as Spotify's output in Spotify > Settings > Playback, or in Windows "
                       "Volume mixer. Keep your real speakers or headphones as the Windows default."
                  ).grid(sticky="w")
        ttk.Button(self.setup, text="Get VB-Cable (vb-audio.com)",
                   command=lambda: os.startfile(device_pick.CABLE_URL)).grid(sticky="w", pady=(6, 0))
        ttk.Button(devices, text="Rescan devices", command=self._rescan).grid(sticky="w", pady=(0, 8))
        self.exclusive_var = tk.BooleanVar(value=bool(self.settings.get("exclusive", False)))
        ttk.Checkbutton(devices, text="Bypass Windows and audio-driver effects (exclusive mode)",
                        variable=self.exclusive_var, command=self._on_exclusive).grid(sticky="w")
        self.exclusive_note = ttk.Label(devices, style="Muted.TLabel", wraplength=410, justify="left",
                                        text="Takes over the headphone jack: every other app goes silent on it "
                                             "while Loud runs.")
        self.exclusive_note.grid(sticky="w", pady=(2, 0))
        self._on_exclusive()
        if startup.available():
            self.startup_var = tk.BooleanVar(value=startup.is_enabled())
            ttk.Checkbutton(devices, text="Start Loud when Windows starts", variable=self.startup_var,
                            command=lambda: startup.set_enabled(self.startup_var.get())).grid(sticky="w", pady=(8, 0))

        boost = ttk.Frame(outer, style="Panel.TFrame", padding=14)
        boost.grid(sticky="ew", pady=(0, 10))
        head = ttk.Frame(boost, style="Panel.TFrame")
        head.grid(sticky="ew")
        ttk.Label(head, text="Boost", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(head, text="Reset to 0 dB", command=self._reset_gain).grid(row=0, column=1, sticky="e")
        head.columnconfigure(0, weight=1)
        self.gain_label = ttk.Label(boost, text="", style="Big.TLabel")
        self.gain_label.grid(sticky="w", pady=(4, 0))
        self.gain_var = tk.DoubleVar(value=0.0)
        self.scale = ttk.Scale(boost, from_=MIN_GAIN_DB, to=MAX_GAIN_DB, variable=self.gain_var,
                               command=self._on_gain, length=410)
        self.scale.grid(sticky="ew", pady=(4, 0))
        ttk.Label(boost, text="Ctrl+Alt+PageUp / PageDown: ±1 dB     Ctrl+Alt+0: reset to 0 dB",
                  style="Muted.TLabel").grid(sticky="w", pady=(6, 0))

        meters = ttk.Frame(outer, style="Panel.TFrame", padding=14)
        meters.grid(sticky="ew", pady=(0, 10))
        meters.columnconfigure(1, weight=1)
        self.m_in, self.m_out, self.m_red = Meter(meters, GOOD), Meter(meters, ACCENT), Meter(meters, WARN)
        for row, (label, meter) in enumerate((("Input", self.m_in), ("Output", self.m_out), ("Limiter", self.m_red))):
            ttk.Label(meters, text=label, style="Muted.TLabel", width=8).grid(row=row, column=0, sticky="w", pady=3)
            meter.grid(row=row, column=1, sticky="ew", pady=3)

        self.button = ttk.Button(outer, text="Start", style="Go.TButton", command=self._toggle)
        self.button.grid(sticky="ew", pady=(0, 8))

        self.status = ttk.Label(outer, text="", wraplength=430, justify="left", style="Sub.TLabel")
        self.status.grid(sticky="w")
        vol = ttk.Frame(outer)
        vol.grid(sticky="ew", pady=(4, 0))
        self.win_volume = ttk.Label(vol, text="", style="Sub.TLabel")
        self.win_volume.grid(row=0, column=0, sticky="w")
        self.max_btn = ttk.Button(vol, text="Set Windows volume to 100%", command=self._max_windows_volume)
        self.max_btn.grid(row=0, column=1, padx=(8, 0))
        self.max_btn.grid_remove()
        ttk.Label(outer, style="Sub.TLabel", wraplength=430, justify="left",
                  text="Tip: in Spotify > Settings > Audio quality, turn off audio normalization (or set the "
                       "volume level to Loud). Otherwise Spotify turns loud songs down before Loud boosts them."
                  ).grid(sticky="w", pady=(10, 0))
        ttk.Label(outer, style="Sub.TLabel", wraplength=430, justify="left",
                  text="Spotify is silent while it's routed to Loud's input and Loud isn't running. To undo, set "
                       "Spotify's output back to Default in Volume mixer."
                  ).grid(sticky="w", pady=(6, 0))
        ttk.Label(outer, text="Very loud sound can damage hearing and headphones. Raise the boost slowly.",
                  style="Sub.TLabel", wraplength=430).grid(sticky="w", pady=(6, 0))
        self._on_gain(0.0)

    # ---- devices ------------------------------------------------------------------------------

    def _refresh_devices(self):
        self.devices = wasapi.list_render_endpoints()
        names = [name for _, name in self.devices]
        self.source["values"], self.output["values"] = names, names

        ids = [ident for ident, _ in self.devices]
        out_id, src_id = device_pick.choose(self.devices, wasapi.default_render_endpoint_id(),
                                            self.settings.get("output"), self.settings.get("source"))
        if out_id in ids:
            self.output.current(ids.index(out_id))
        if src_id in ids:
            self.source.current(ids.index(src_id))
        else:
            self.source.set("")
        if src_id is None:
            self.setup.grid()
        else:
            self.setup.grid_remove()

    def _rescan(self):
        self.settings = {"output": self._selected(self.output)[0], "source": self._selected(self.source)[0]}
        self._refresh_devices()
        self._update_spotify()

    def _selected(self, combo):
        index = combo.current()
        return self.devices[index] if 0 <= index < len(self.devices) else (None, "")

    def _on_exclusive(self):
        if self.exclusive_var.get():
            self.exclusive_note.grid()
        else:
            self.exclusive_note.grid_remove()

    def _update_spotify(self):
        src_id, _ = self._selected(self.source)
        out_id, _ = self._selected(self.output)
        if not out_id:
            self.spotify_msg.configure(text="No playback devices found.", foreground=BAD)
            return
        if not src_id:
            self.spotify_msg.configure(text="Waiting for a second audio device to listen on (see above).",
                                       foreground=WARN)
            return
        if src_id == out_id:
            self.spotify_msg.configure(text="Pick two different devices: your headphones, and a separate output "
                                            "for Loud to listen on.", foreground=WARN)
            return
        state = spotify.check([ident for ident, _ in self.devices])
        level, text = spotify.advice(state, src_id, out_id, dict(self.devices))
        self.spotify_msg.configure(text=text, foreground=LEVEL_COLORS[level])

    # ---- boost --------------------------------------------------------------------------------

    def _on_gain(self, value):
        db = round(float(value) * 2) / 2
        if self.engine:
            self.engine.gain_db = db
        percent = 100 * 10 ** (db / 20)
        self.gain_label.configure(text=f"{db:+.1f} dB   ≈ {percent:.0f}%")

    def _set_gain(self, db):
        self.gain_var.set(min(max(db, MIN_GAIN_DB), MAX_GAIN_DB))
        self._on_gain(self.gain_var.get())

    def _reset_gain(self):
        self._set_gain(0.0)

    # ---- start / stop -------------------------------------------------------------------------

    def _toggle(self):
        if self.engine:
            self._stop(user=True)
        else:
            self._start()

    def _start(self):
        if self.engine:
            return
        src_id, _ = self._selected(self.source)
        out_id, _ = self._selected(self.output)
        if not src_id or not out_id or src_id == out_id:
            self._set_status("Loud needs a second, silent audio device to listen on. See the notice above.", BAD)
            return
        engine = Engine(src_id, out_id, exclusive=self.exclusive_var.get())
        engine.gain_db = round(self.gain_var.get() * 2) / 2
        try:
            engine.start()
        except wasapi.WasapiError as e:
            log.warning("start failed: %s", e)
            self._set_status(f"Could not start: {e}", BAD)
            return
        self.engine = engine
        self._remember(autostart=True)
        for widget in (self.source, self.output):
            widget.configure(state="disabled")
        self.button.configure(text="Stop", style="Stop.TButton")
        self._set_status(f"Running: {engine.info}", GOOD)

    def _stop(self, message="Stopped. Spotify stays silent until Loud runs again, or until you route it back "
                            "to Default in Volume mixer.", user=False):
        if self.engine:
            self.engine.stop()
            self.engine = None
        if user:
            self._remember(autostart=False)
        self.source.configure(state="readonly")
        self.output.configure(state="readonly")
        self.button.configure(text="Start", style="Go.TButton")
        self._set_status(message, MUTED)

    def _remember(self, autostart):
        src_id, _ = self._selected(self.source)
        out_id, _ = self._selected(self.output)
        save_settings({"source": src_id, "output": out_id, "exclusive": self.exclusive_var.get(),
                       "autostart": autostart})

    def _set_status(self, text, color):
        self.status.configure(text=text, foreground=color)

    def _on_error(self, exc_type, exc, tb):
        log.error("UI error", exc_info=(exc_type, exc, tb))
        self._set_status(f"Something went wrong ({exc_type.__name__}: {exc}). Details are in {LOG_PATH}", BAD)

    def _close(self):
        self._stop()
        self.root.destroy()

    # ---- periodic UI refresh ------------------------------------------------------------------

    def _max_windows_volume(self):
        out_id, _ = self._selected(self.output)
        if out_id:
            wasapi.set_endpoint_volume(out_id, 1.0)

    def _tick(self):
        self._ticks += 1
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "reset":
                self._reset_gain()
            else:
                self._set_gain(self.gain_var.get() + (1.0 if event == "up" else -1.0))

        if self.engine and not self.engine.running:
            reason = self.engine.error or "the audio device went away (is the monitor on?)"
            self._stop(f"Stopped: {reason}")
            self.status.configure(foreground=BAD)

        if self.engine:
            in_peak, out_peak, reduction = self.engine.meters.take()
            self.m_in.show(self._db_fraction(in_peak))
            self.m_out.show(self._db_fraction(out_peak), BAD if out_peak > 0.95 else None)
            self.m_red.show(min(reduction / 18.0, 1.0))
        else:
            for meter in (self.m_in, self.m_out, self.m_red):
                meter.show(0.0)

        if self._ticks % 20 == 1:
            self._update_spotify()
            out_id, _ = self._selected(self.output)
            level = wasapi.get_endpoint_volume(out_id) if out_id else None
            if level is None:
                self.win_volume.configure(text="")
                self.max_btn.grid_remove()
            else:
                low = level < 0.995
                self.win_volume.configure(text=f"Windows volume on headphones: {level * 100:.0f}%",
                                          foreground=WARN if low else MUTED)
                self.max_btn.grid() if low else self.max_btn.grid_remove()
        self.root.after(50, self._tick)

    @staticmethod
    def _db_fraction(peak):
        db = 20 * math.log10(max(peak, 1e-6))
        return max(0.0, (db + 60.0) / 60.0)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    logging.basicConfig(filename=LOG_PATH, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (OSError, AttributeError):
        pass
    wasapi.init_com()
    root = tk.Tk()
    App(root)
    root.mainloop()
