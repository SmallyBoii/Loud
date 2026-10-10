"""Gain and look-ahead limiter. Block-size independent: state carries across calls."""
import math

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

MAX_GAIN_DB = 24.0
MIN_GAIN_DB = -24.0


def db_to_lin(db):
    return 10.0 ** (db / 20.0)


def lin_to_db(x):
    return 20.0 * math.log10(max(x, 1e-9))


class Limiter:
    """Brick-wall peak limiter for stereo float audio.

    It delays the audio by `lookahead_ms` and starts turning the gain down that long before a peak
    arrives, so the output never exceeds `ceiling_db` and the gain change is smooth rather than a
    hard clip. Afterwards the gain recovers over roughly `release_ms`.
    """

    def __init__(self, rate, ceiling_db=-0.3, lookahead_ms=3.0, release_ms=120.0):
        self.look = max(1, int(rate * lookahead_ms / 1000.0))
        self.ceiling = db_to_lin(ceiling_db)
        self.release = math.exp(-1.0 / (rate * release_ms / 1000.0))
        self._audio = np.zeros((self.look, 2), dtype=np.float32)   # samples waiting to be output
        self._required = np.ones(self.look, dtype=np.float32)      # gain each of those samples needs
        self._floor_hist = np.ones(self.look - 1, dtype=np.float32)
        self._gain = 1.0

    @property
    def latency_frames(self):
        return self.look

    def process(self, block):
        """Limit an (N, 2) float32 block. Returns (output, lowest_gain_used); output is delayed by `latency_frames`."""
        n = len(block)
        if n == 0:
            return block, 1.0
        peak = np.abs(block).max(axis=1)
        required = np.minimum(1.0, self.ceiling / np.maximum(peak, 1e-9)).astype(np.float32)
        ext_required = np.concatenate([self._required, required])
        ext_audio = np.concatenate([self._audio, block])

        # Lowest requirement among this sample and the next `look` samples: gain starts falling early.
        floor = sliding_window_view(ext_required, self.look + 1).min(axis=1)
        # Average it over the last `look` samples so the fall is a smooth ramp that lands on the peak.
        ext_floor = np.concatenate([self._floor_hist, floor])
        csum = np.concatenate([[0.0], np.cumsum(ext_floor, dtype=np.float64)])
        target = ((csum[self.look:] - csum[:-self.look]) / self.look).tolist()

        gain, r = self._gain, self.release
        gains = [0.0] * n
        for i, t in enumerate(target):
            gain = t if t < gain else r * gain + (1.0 - r) * t
            gains[i] = gain
        self._gain = gain

        self._audio = ext_audio[n:]
        self._required = ext_required[n:]
        self._floor_hist = ext_floor[n:]
        g = np.asarray(gains, dtype=np.float32)
        out = ext_audio[:n] * g[:, None]
        np.clip(out, -self.ceiling, self.ceiling, out=out)
        return out, float(g.min())


class GainStage:
    """Smoothed gain with a slow fade-in after start, so nothing ever jumps to full level."""

    def __init__(self, rate, fade_in_s=1.5):
        self._rate = rate
        self._fade_frames = max(1, int(rate * fade_in_s))
        self._played = 0
        self._current = 0.0

    def process(self, block, target_db, mute=False):
        n = len(block)
        if n == 0:
            return block
        target = 0.0 if mute else db_to_lin(min(max(target_db, MIN_GAIN_DB), MAX_GAIN_DB))
        ramp = self._current + (target - self._current) * (np.arange(1, n + 1, dtype=np.float32) / n)
        self._current = target
        if self._played < self._fade_frames:
            progress = np.clip((self._played + np.arange(n)) / self._fade_frames, 0.0, 1.0)
            ramp = ramp * (progress * progress).astype(np.float32)
            self._played += n
        return block * ramp[:, None]
