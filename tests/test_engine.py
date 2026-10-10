"""Engine loop against simulated devices that run in real time. Nothing touches real audio hardware."""
import threading
import time
import unittest

import numpy as np

from loud.dsp import db_to_lin
from loud.engine import Engine

RATE = 48000


class FakeCapture:
    """Delivers 10 ms packets of a sine on the wall clock, optionally with a silent gap (no packets)."""

    def __init__(self, amp=0.5, silent_from=None, silent_until=None):
        self.rate = RATE
        self.amp, self.silent_from, self.silent_until = amp, silent_from, silent_until
        self._t0 = time.monotonic()
        self._delivered = 0
        self.closed = False

    def read(self):
        elapsed = time.monotonic() - self._t0
        due = int(elapsed * RATE) - self._delivered
        if due < RATE // 100:
            return np.zeros((0, 2), dtype=np.float32)
        t = (np.arange(due) + self._delivered) / RATE
        self._delivered += due
        if self.silent_from is not None and self.silent_from <= elapsed < self.silent_until:
            return np.zeros((0, 2), dtype=np.float32)
        mono = (self.amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        return np.stack([mono, mono], axis=1)

    def close(self):
        self.closed = True


class FakeRender:
    """A device that drains its queue at real-time speed and records everything written to it."""

    buffer_frames = int(RATE * 0.04)
    period_frames = int(RATE * 0.01)

    def __init__(self):
        self._lock = threading.Lock()
        self._queued = 0.0
        self._last = time.monotonic()
        self.written = []
        self.underruns = 0
        self.started = False
        self.closed = False

    def describe(self):
        return "fake output"

    def _drain(self):
        now = time.monotonic()
        if self.started:
            self._queued -= (now - self._last) * RATE
            if self._queued < 0:
                self.underruns += 1
                self._queued = 0.0
        self._last = now

    def prefill(self, frames):
        self._queued, self.started, self._last = float(frames), True, time.monotonic()

    def queued(self):
        self._drain()
        return int(self._queued)

    def free(self):
        self._drain()
        return self.buffer_frames - int(self._queued)

    def write(self, block):
        self._drain()
        self._queued += len(block)
        self.written.append(block.copy())

    def close(self):
        self.closed = True


def run_engine(capture, render, gain_db, seconds):
    engine = Engine("src", "out", open_devices=lambda s, o: (capture, render))
    engine.gain_db = gain_db
    engine.start()
    time.sleep(seconds)
    engine.stop()
    return engine


class EngineTests(unittest.TestCase):
    def test_streams_audio_limited_and_without_underruns(self):
        cap, ren = FakeCapture(amp=0.5), FakeRender()
        engine = run_engine(cap, ren, gain_db=18.0, seconds=1.5)
        self.assertIsNone(engine.error)
        out = np.concatenate(ren.written)
        self.assertGreater(len(out), RATE)                      # about 1.5 s of audio flowed
        self.assertLessEqual(np.abs(out).max(), db_to_lin(-0.3) + 1e-6)
        self.assertGreater(np.abs(out[RATE:]).max(), 0.9)       # boosted well above the 0.5 input
        self.assertLessEqual(ren.underruns, 1)
        self.assertTrue(cap.closed and ren.closed)

    def test_fades_in_instead_of_starting_at_full_level(self):
        cap, ren = FakeCapture(amp=0.5), FakeRender()
        run_engine(cap, ren, gain_db=12.0, seconds=1.0)
        out = np.concatenate(ren.written)
        self.assertLess(np.abs(out[:RATE // 50]).max(), 0.05)   # first 20 ms nearly silent

    def test_recovers_after_capture_goes_silent(self):
        cap, ren = FakeCapture(amp=0.5, silent_from=0.4, silent_until=0.9), FakeRender()
        engine = run_engine(cap, ren, gain_db=6.0, seconds=1.8)
        self.assertIsNone(engine.error)
        out = np.concatenate(ren.written)
        self.assertGreater(np.abs(out[-RATE // 4:]).max(), 0.1)  # audio is flowing again at the end

    def test_stop_fades_out(self):
        cap, ren = FakeCapture(amp=0.5), FakeRender()
        run_engine(cap, ren, gain_db=12.0, seconds=1.5)
        out = np.concatenate(ren.written)
        self.assertLess(np.abs(out[-RATE // 100:]).max(), 0.05)  # ends near silence, no click

    def test_open_failure_is_reported(self):
        def boom(s, o):
            raise OSError("device gone")
        engine = Engine("src", "out", open_devices=boom)
        with self.assertRaises(Exception):
            engine.start()

    def test_unexpected_crash_surfaces_a_message_instead_of_dying_silently(self):
        def boom(s, o):
            raise ValueError("something odd")
        engine = Engine("src", "out", open_devices=boom)
        with self.assertRaises(Exception) as ctx:
            engine.start()
        self.assertIn("unexpected error", str(ctx.exception))
        self.assertIn("something odd", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
