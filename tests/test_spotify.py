import unittest

from loud.spotify import SpotifyState, advice

NAMES = {"src": "Monitor", "out": "Realtek", "other": "USB DAC"}


def level(**kw):
    return advice(SpotifyState(**kw), "src", "out", NAMES)


class AdviceTests(unittest.TestCase):
    def test_not_running(self):
        self.assertEqual(level(running=False)[0], "info")

    def test_playing_into_loud_is_ok(self):
        self.assertEqual(level(running=True, playing_on="src", seen_on={"src"})[0], "ok")

    def test_playing_straight_to_headphones_warns_and_names_the_fix(self):
        lvl, text = level(running=True, playing_on="out", seen_on={"out"})
        self.assertEqual(lvl, "warn")
        self.assertIn("Volume mixer", text)
        self.assertIn("Monitor", text)

    def test_playing_on_a_third_device_warns(self):
        self.assertEqual(level(running=True, playing_on="other", seen_on={"other"})[0], "warn")

    def test_idle_but_routed_is_ok(self):
        self.assertEqual(level(running=True, seen_on={"src", "out"})[0], "ok")

    def test_idle_and_only_seen_elsewhere_warns(self):
        self.assertEqual(level(running=True, seen_on={"out"})[0], "warn")

    def test_open_but_never_played_is_just_info(self):
        self.assertEqual(level(running=True)[0], "info")


if __name__ == "__main__":
    unittest.main()
