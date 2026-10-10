import os

DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Loud")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
LOG_PATH = os.path.join(DATA_DIR, "loud.log")
