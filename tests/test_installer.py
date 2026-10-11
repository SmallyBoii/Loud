"""The installer scripts, run for real but only into a scratch folder: no shortcut, no Apps entry, no start-with-Windows value."""
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POWERSHELL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


def run_ps(script, *args, env=None):
    cmd = [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(ROOT, script), *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)


class ScriptTests(unittest.TestCase):
    def test_scripts_parse(self):
        for script in ("install.ps1", "uninstall.ps1", "build.ps1", os.path.join("tools", "package.ps1")):
            path = os.path.join(ROOT, script)
            check = ("$e = $null; [void][System.Management.Automation.Language.Parser]::ParseFile('%s', [ref]$null, [ref]$e); "
                     "if ($e) { $e | ForEach-Object { $_.Message }; exit 1 }" % path)
            done = subprocess.run([POWERSHELL, "-NoProfile", "-Command", check], capture_output=True, text=True, timeout=60)
            self.assertEqual(done.returncode, 0, f"{script}: {done.stdout}{done.stderr}")

    def test_batch_file_starts_powershell_from_the_system_folder(self):
        with open(os.path.join(ROOT, "Install Loud.bat"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn(r"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe", text)
        self.assertIn("install.ps1", text)


class InstallRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="loud-test-")
        self.source = os.path.join(self.tmp, "src")
        os.makedirs(self.source)
        with open(os.path.join(self.source, "Loud.exe"), "wb") as f:
            f.write(b"MZ stand-in program for the installer test")
        self.target = os.path.join(self.tmp, "Programs", "Loud")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def install(self):
        return run_ps("install.ps1", "-Yes", "-NoStart", "-NoShortcut", "-NoUninstallEntry",
                      "-Source", self.source, "-InstallDir", self.target)

    def test_install_copies_the_files_and_uninstall_removes_them(self):
        done = self.install()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        for name in ("Loud.exe", "uninstall.ps1", "LICENSE", "THIRD-PARTY-NOTICES.md"):
            self.assertTrue(os.path.exists(os.path.join(self.target, name)), name)
        self.assertTrue(os.path.isdir(os.path.join(self.target, "licenses")))

        done = run_ps("uninstall.ps1", "-Yes", "-KeepData", "-NoShortcut", "-NoUninstallEntry", "-InstallDir", self.target)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertFalse(os.path.exists(self.target))

    def test_works_with_a_powershell_7_style_module_path(self):
        # A pwsh window or a CI step hands its own module path down to Windows PowerShell 5.1, which then cannot find Get-FileHash.
        env = dict(os.environ, PSModulePath=r"C:\Program Files\PowerShell\Modules")
        done = run_ps("install.ps1", "-Yes", "-NoStart", "-NoShortcut", "-NoUninstallEntry",
                      "-Source", self.source, "-InstallDir", self.target, env=env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        done = run_ps("uninstall.ps1", "-Yes", "-KeepData", "-NoShortcut", "-NoUninstallEntry", "-InstallDir", self.target, env=env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_reinstall_over_an_existing_install_works(self):
        self.assertEqual(self.install().returncode, 0)
        done = self.install()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_refuses_a_drive_root(self):
        done = run_ps("install.ps1", "-Yes", "-NoStart", "-NoShortcut", "-NoUninstallEntry",
                      "-Source", self.source, "-InstallDir", "C:\\")
        self.assertNotEqual(done.returncode, 0)

    def test_uninstall_refuses_a_folder_that_is_not_a_loud_install(self):
        other = os.path.join(self.tmp, "Programs", "SomethingElse")
        os.makedirs(other)
        with open(os.path.join(other, "precious.txt"), "w") as f:
            f.write("keep me")
        done = run_ps("uninstall.ps1", "-Yes", "-KeepData", "-NoShortcut", "-NoUninstallEntry", "-InstallDir", other)
        self.assertNotEqual(done.returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(other, "precious.txt")))

    def test_install_fails_clearly_without_a_program_to_install(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        done = run_ps("install.ps1", "-Yes", "-NoStart", "-NoShortcut", "-NoUninstallEntry",
                      "-Source", empty, "-InstallDir", self.target)
        self.assertNotEqual(done.returncode, 0)
        self.assertFalse(os.path.exists(self.target))


if __name__ == "__main__":
    unittest.main()
