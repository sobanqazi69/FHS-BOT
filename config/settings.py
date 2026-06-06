import json
import os


class Settings:
    def __init__(self):
        self._data = {}
        # Use working directory (set to exe location by app.py) so it works both
        # as a plain script and as a PyInstaller exe.
        config_file = os.path.join(os.getcwd(), "config", "config.json")
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                self._data = json.load(f)

    def get(self, key, default=None):
        return self._data.get(key, default)
