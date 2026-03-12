import os
import shutil
import tempfile
import unittest

from app_settings import AppSettings
from localization import Localizer


class TestAppSettings(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "app_settings.json")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_language_persists(self):
        settings = AppSettings(self.path)
        settings.language = "ru"
        settings.save()

        loaded = AppSettings(self.path)
        self.assertEqual(loaded.language, "ru")


class TestLocalizer(unittest.TestCase):
    def test_russian_profile_is_available(self):
        localizer = Localizer()
        self.assertIn(("ru", "Русский"), localizer.available_languages())

    def test_falls_back_to_english_for_missing_key(self):
        localizer = Localizer()
        localizer.set_language("ru")
        self.assertEqual(localizer.translate("missing.key"), "missing.key")
        self.assertEqual(localizer.translate("abilities.str.abbr"), "СИЛ")
        self.assertIn("Класс Доспеха", localizer.translate("combat.ac.tooltip"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
