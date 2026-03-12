import json
import os


LOCALES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
DEFAULT_LANGUAGE = "en"


class Localizer:
    def __init__(self, locales_dir: str = LOCALES_DIR, default_language: str = DEFAULT_LANGUAGE):
        self._locales_dir = locales_dir
        self._default_language = default_language
        self._translations = self._load_translations()
        self._language = default_language if default_language in self._translations else next(iter(self._translations), "en")

    def _load_translations(self) -> dict[str, dict[str, str]]:
        translations: dict[str, dict[str, str]] = {}
        if not os.path.isdir(self._locales_dir):
            return translations
        for filename in sorted(os.listdir(self._locales_dir)):
            if not filename.endswith(".json"):
                continue
            language = os.path.splitext(filename)[0]
            path = os.path.join(self._locales_dir, filename)
            with open(path, "r", encoding="utf-8") as file:
                translations[language] = json.load(file)
        return translations

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str):
        if language in self._translations:
            self._language = language
        elif self._default_language in self._translations:
            self._language = self._default_language

    def available_languages(self) -> list[tuple[str, str]]:
        result = []
        for language in sorted(self._translations):
            label = self._translations[language].get("_meta.label", language)
            result.append((language, label))
        return result

    def translate(self, key: str, **kwargs) -> str:
        template = self._translations.get(self._language, {}).get(key)
        if template is None:
            template = self._translations.get(self._default_language, {}).get(key, key)
        if kwargs:
            try:
                return str(template).format(**kwargs)
            except (KeyError, ValueError):
                return str(template)
        return str(template)


_LOCALIZER = Localizer()


def set_language(language: str):
    _LOCALIZER.set_language(language)


def get_language() -> str:
    return _LOCALIZER.language


def language_options() -> list[tuple[str, str]]:
    return _LOCALIZER.available_languages()


def t(key: str, **kwargs) -> str:
    return _LOCALIZER.translate(key, **kwargs)


def ability_label(stat_key: str) -> str:
    return t(f"abilities.{stat_key}.abbr")


def ability_tooltip(stat_key: str) -> str:
    return t(f"abilities.{stat_key}.tooltip")


def combat_stat_tooltip(stat_key: str) -> str:
    return t(f"combat.{stat_key}.tooltip")
