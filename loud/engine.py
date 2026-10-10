"""Real-time loop: loopback capture -> gain -> limiter -> exclusive-mode headphone output."""
import ctypes
import logging
import threading
import time
from collections import deque
from ctypes import byref, wintypes

import numpy as np

from . import wasapi
from .config import LOG_PATH
from .dsp import GainStage, Limiter, lin_to_db

log = logging.getLogger("loud")

POLL_S = 0.002
TARGET_QUEUE_S = 0.025      # audio kept queued in the output device: the main latency knob
LOW_WATER_S = 0.006         # below this with nothing to play, the output gets silence instead of starving
PRIME_S = 0.012             # audio to accumulate before (re)starting playback after a gap
RING_HIGH_S = 0.080         # capture backlog beyond this means the two clocks drifted; trim it
RING_TRIM_TO_S = 0.030
FADE_OUT_S = 0.05


class Meters:
    """Peaks accumulated since the last `take()`, so the UI sees silence as silence."""

    def __init__(self):
        self.in_peak = 0.0
        self.out_peak = 0.0
        self.reduction_db = 0.0

    def take(self):
        values = (self.in_peak, self.out_peak, self.reduction_db)
        self.in_peak = self.out_peak = self.reduction_db = 0.0
        return values


class _Ring:
    def __init__(self):
        self._chunks = deque()
        self.frames = 0

    def push(self, block):
        self._chunks.append(block)
        self.frames += len(block)

    def take(self, n):
        out, left = [], n
        while left > 0 and self._chunks:
            head = self._chunks[0]
            if len(head) <= left:
                out.append(head)
                self._chunks.popleft()
                left -= len(head)
            else:
                out.append(head[:left])
                self._chunks[0] = head[left:]
                left = 0
        self.frames -= n - left
        return np.concatenate(out) if out else np.zeros((0, 2), dtype=np.float32)

    def trim_to(self, n):
        if self.frames > n:
            self.take(self.frames - n)


def _boost_thread_priority():
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
        ctypes.windll.avrt.AvSetMmThreadCharacteristicsW("Pro Audio", byref(wintypes.DWORD(0)))
    except (OSError, AttributeError):
        pass


def _open_wasapi(source_id, output_id, exclusive):
    capture = wasapi.LoopbackCapture(source_id)
    try:
        render_class = wasapi.ExclusiveRender if exclusive else wasapi.SharedRender
        return capture, render_class(output_id, capture.rate)
    except Exception:
        capture.close()
        raise


class Engine:
    """`exclusive=False` plays into the normal Windows mixer (other apps keep working);
    `exclusive=True` takes the output over and bypasses Windows effects."""

    def __init__(self, source_id, output_id, exclusive=False, open_devices=None):
        self.source_id = source_id
        self.output_id = output_id
        self.exclusive = exclusive
        self._open_devices = open_devices or (lambda src, out: _open_wasapi(src, out, exclusive))
        self.gain_db = 0.0
        self.meters = Meters()
        self.error = None
        self.info = ""
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="loud-engine", daemon=True)

    @property
    def running(self):
        return self._thread.is_alive()

    def start(self, timeout=5.0):
        """Open the devices and start streaming. Raises wasapi.WasapiError if that fails."""
        self._thread.start()
        if not self._ready.wait(timeout):
            self._stop.set()
            raise wasapi.WasapiError("timed out opening the audio devices")
        if self.error:
            raise wasapi.WasapiError(self.error)

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2.0)

    def _run(self):
        wasapi.init_com()
        _boost_thread_priority()
        capture = render = None
        try:
            capture, render = self._open_devices(self.source_id, self.output_id)
            rate = capture.rate
            target = min(int(rate * TARGET_QUEUE_S), int(render.buffer_frames * 0.6))
            low_water = int(rate * LOW_WATER_S)
            prime = int(rate * PRIME_S)
            ring, gain, limiter = _Ring(), GainStage(rate), Limiter(rate)
            render.prefill(target)
            self.info = (f"{render.describe()}, "
                         f"~{(target + limiter.latency_frames) * 1000 // rate} ms added latency")
            self._ready.set()
            self._stream(capture, render, ring, gain, limiter, rate, target, low_water, prime)
        except (wasapi.WasapiError, OSError) as e:
            self.error = str(e) if isinstance(e, wasapi.WasapiError) else wasapi.explain(e)
            log.warning("engine stopped: %s", self.error)
        except Exception as e:  # anything unexpected: report it rather than dying silently
            log.exception("engine crashed")
            self.error = f"unexpected error ({type(e).__name__}: {e}); details are in {LOG_PATH}"
        finally:
            for dev in (render, capture):
                if dev is not None:
                    dev.close()
            self._ready.set()

    def _stream(self, capture, render, ring, gain, limiter, rate, target, low_water, prime):
        playing = False
        fade_out_until = None
        while True:
            if self._stop.is_set() and fade_out_until is None:
                fade_out_until = time.monotonic() + FADE_OUT_S
            if fade_out_until is not None and time.monotonic() >= fade_out_until:
                return

            fresh = capture.read()
            if len(fresh):
                ring.push(fresh)
                self.meters.in_peak = max(self.meters.in_peak, float(np.abs(fresh).max()))
            if ring.frames > int(rate * RING_HIGH_S):
                ring.trim_to(int(rate * RING_TRIM_TO_S))
            if not playing and ring.frames >= prime:
                playing = True

            queued = render.queued()
            room = min(target - queued, render.free())
            if room < max(1, render.period_frames // 4):
                time.sleep(POLL_S)
                continue

            if playing and ring.frames > 0:
                block = ring.take(min(room, ring.frames))
            elif queued < low_water:
                block = np.zeros((room, 2), dtype=np.float32)
                playing = False
            else:
                time.sleep(POLL_S)
                continue

            block = gain.process(block, self.gain_db, mute=fade_out_until is not None)
            block, lowest = limiter.process(block)
            render.write(block)
            self.meters.out_peak = max(self.meters.out_peak, float(np.abs(block).max()))
            self.meters.reduction_db = max(self.meters.reduction_db, -lin_to_db(lowest))
            time.sleep(POLL_S)
