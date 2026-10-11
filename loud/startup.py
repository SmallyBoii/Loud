"""Optional 'start Loud when Windows starts', via the per-user Run registry key (no admin needed)."""
import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "Loud"


def available():
    """Only the packaged Loud.exe can register itself; a source checkout has no stable path to run."""
    return bool(getattr(sys, "frozen", False))


def command():
    return f'"{sys.executable}"'


def is_enabled(key=RUN_KEY, name=NAME):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return winreg.QueryValueEx(k, name)[0] == command()
    except OSError:
        return False


def set_enabled(enabled, key=RUN_KEY, name=NAME):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
        if enabled:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(k, name)
            except FileNotFoundError:
                pass
