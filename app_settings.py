import json
import os


SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_settings.json")
DEFAULT_SETTINGS = {
    "language": "en",
}


class AppSettings:
    def __init__(self, path: str = SETTINGS_PATH):
        self._path = path
        self._data = dict(DEFAULT_SETTINGS)
        self.load()

    @property
    def path(self) -> str:
        return self._path

    @property
    def language(self) -> str:
        return str(self._data.get("language", DEFAULT_SETTINGS["language"]) or DEFAULT_SETTINGS["language"])

    @language.setter
    def language(self, value: str):
        self._data["language"] = str(value or DEFAULT_SETTINGS["language"])

    def load(self):
        if not os.path.isfile(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as file:
                loaded = json.load(file)
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(loaded, dict):
            self._data.update(loaded)

    def save(self):
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as file:
            json.dump(self._data, file, ensure_ascii=False, indent=2)
