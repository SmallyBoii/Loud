import unittest
import winreg

from loud import startup

TEST_KEY = r"Software\LoudTests\Run"


class StartupTests(unittest.TestCase):
    def tearDown(self):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, TEST_KEY)
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\LoudTests")
        except OSError:
            pass

    def test_off_by_default(self):
        self.assertFalse(startup.is_enabled(TEST_KEY))

    def test_enable_then_disable(self):
        startup.set_enabled(True, TEST_KEY)
        self.assertTrue(startup.is_enabled(TEST_KEY))
        startup.set_enabled(False, TEST_KEY)
        self.assertFalse(startup.is_enabled(TEST_KEY))

    def test_disable_when_never_enabled_is_harmless(self):
        startup.set_enabled(False, TEST_KEY)

    def test_command_quotes_the_path(self):
        self.assertTrue(startup.command().startswith('"') and startup.command().endswith('"'))

    def test_not_available_from_source(self):
        self.assertFalse(startup.available())


if __name__ == "__main__":
    unittest.main()
