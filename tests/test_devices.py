import unittest

from loud.devices import choose, is_virtual

SPEAKERS = ("spk", "Speakers (Realtek(R) Audio)")
MONITOR = ("mon", "25G3ZM (AMD High Definition Audio Device)")
CABLE = ("cab", "CABLE Input (VB-Audio Virtual Cable)")


class VirtualTests(unittest.TestCase):
    def test_recognises_virtual_devices(self):
        self.assertTrue(is_virtual(CABLE[1]))
        self.assertTrue(is_virtual("VoiceMeeter Input (VB-Audio VoiceMeeter VAIO)"))
        self.assertFalse(is_virtual(SPEAKERS[1]))
        self.assertFalse(is_virtual(MONITOR[1]))


class ChooseTests(unittest.TestCase):
    def test_single_real_device_has_no_source(self):
        self.assertEqual(choose([SPEAKERS], "spk"), ("spk", None))

    def test_cable_becomes_the_source_and_default_stays_the_output(self):
        self.assertEqual(choose([SPEAKERS, CABLE], "spk"), ("spk", "cab"))

    def test_cable_is_preferred_over_a_monitor(self):
        self.assertEqual(choose([SPEAKERS, MONITOR, CABLE], "spk"), ("spk", "cab"))

    def test_monitor_is_used_when_there_is_no_cable(self):
        self.assertEqual(choose([SPEAKERS, MONITOR], "spk"), ("spk", "mon"))

    def test_windows_default_being_the_cable_does_not_make_it_the_output(self):
        self.assertEqual(choose([CABLE, SPEAKERS], "cab"), ("spk", "cab"))

    def test_saved_choices_win_when_still_present(self):
        self.assertEqual(choose([SPEAKERS, MONITOR, CABLE], "spk", "spk", "mon"), ("spk", "mon"))

    def test_stale_saved_choices_are_ignored(self):
        self.assertEqual(choose([SPEAKERS, CABLE], "spk", "gone", "gone"), ("spk", "cab"))

    def test_saved_source_equal_to_output_is_replaced(self):
        self.assertEqual(choose([SPEAKERS, CABLE], "spk", "spk", "spk"), ("spk", "cab"))


if __name__ == "__main__":
    unittest.main()
