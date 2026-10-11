import unittest

import numpy as np

from loud.dsp import GainStage, Limiter, db_to_lin, soft_clip

RATE = 48000


def tone(seconds, amp, freq=440.0):
    t = np.arange(int(RATE * seconds)) / RATE
    mono = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([mono, mono * 0.8], axis=1)


def run_in_blocks(limiter, audio, sizes):
    out, i, k = [], 0, 0
    while i < len(audio):
        n = sizes[k % len(sizes)]
        out.append(limiter.process(audio[i:i + n])[0])
        i += n
        k += 1
    return np.concatenate(out)


class LimiterTests(unittest.TestCase):
    def test_never_exceeds_ceiling_even_at_24_db_boost(self):
        lim = Limiter(RATE, ceiling_db=-0.3)
        boosted = tone(2.0, 0.9) * db_to_lin(24.0)
        out = run_in_blocks(lim, boosted, [480])
        self.assertLessEqual(np.abs(out).max(), db_to_lin(-0.3) + 1e-6)

    def test_quiet_audio_passes_unchanged_apart_from_delay(self):
        lim = Limiter(RATE)
        audio = tone(1.0, 0.1)
        out = run_in_blocks(lim, audio, [480])
        d = lim.latency_frames
        np.testing.assert_allclose(out[d:], audio[:-d], atol=1e-6)

    def test_block_size_does_not_change_the_result(self):
        audio = tone(1.0, 0.8) * db_to_lin(12.0)
        a = run_in_blocks(Limiter(RATE), audio, [480])
        b = run_in_blocks(Limiter(RATE), audio, [1, 7, 333, 64, 1000, 5])
        np.testing.assert_allclose(a, b, atol=1e-6)

    def test_gain_recovers_after_a_peak(self):
        lim = Limiter(RATE, release_ms=50.0)
        loud = tone(0.2, 0.9) * db_to_lin(18.0)
        quiet = tone(1.0, 0.05)
        out = run_in_blocks(lim, np.concatenate([loud, quiet]), [480])
        tail = out[-RATE // 10:]
        expected = quiet[-RATE // 10:]
        # After 0.9 s of quiet material the level is back to within 0.1 dB of untouched.
        ratio = np.abs(tail).max() / np.abs(expected).max()
        self.assertGreater(ratio, 0.99)

    def test_loud_boosted_material_ends_up_louder_than_original(self):
        audio = tone(2.0, 0.3)
        out = run_in_blocks(Limiter(RATE), audio * db_to_lin(12.0), [480])
        rms = lambda x: float(np.sqrt(np.mean(x ** 2)))
        self.assertGreater(rms(out[RATE:]), rms(audio[RATE:]) * 2.5)


class GainStageTests(unittest.TestCase):
    def test_fades_in_from_silence(self):
        stage = GainStage(RATE, fade_in_s=1.0)
        first = stage.process(np.ones((480, 2), dtype=np.float32), 0.0)
        self.assertLess(first.max(), 0.01)
        for _ in range(120):
            last = stage.process(np.ones((480, 2), dtype=np.float32), 0.0)
        self.assertAlmostEqual(float(last[-1, 0]), 1.0, places=3)

    def test_target_is_clamped(self):
        stage = GainStage(RATE, fade_in_s=0.001)
        for _ in range(10):
            out = stage.process(np.ones((480, 2), dtype=np.float32), 100.0)
        self.assertAlmostEqual(float(out[-1, 0]), db_to_lin(24.0), places=2)


class SoftClipTests(unittest.TestCase):
    def test_leaves_quiet_audio_almost_unchanged(self):
        quiet = tone(0.1, 0.01)
        np.testing.assert_allclose(soft_clip(quiet), quiet, atol=1e-5)

    def test_never_exceeds_full_scale_even_with_huge_input(self):
        self.assertLessEqual(np.abs(soft_clip(tone(0.1, 50.0))).max(), 1.0)

    def test_makes_a_driven_signal_denser_than_peak_limiting_alone(self):
        driven = tone(1.0, 4.0)
        limited = Limiter(RATE).process(driven)[0]
        clipped = Limiter(RATE).process(soft_clip(driven))[0]
        rms = lambda x: float(np.sqrt(np.mean(x[RATE // 2:] ** 2)))
        self.assertGreater(rms(clipped), rms(limited))


if __name__ == "__main__":
    unittest.main()
