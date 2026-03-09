"""
test_app.py -- smoke tests for audio_engine and library
"""
import os
import sys
import struct
import wave
import math
import tempfile
import unittest

os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["SDL_VIDEODRIVER"] = "dummy"

sys.path.insert(0, os.path.dirname(__file__))

from audio_engine import MusicEngine
from library import Library, Track, LIB_DIR, LIB_JSON


def make_wav(path: str, duration: float = 0.5, freq: int = 440) -> str:
    sr = 44100
    n = int(sr * duration)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        data = b"".join(
            struct.pack("<h", int(32767 * math.sin(2 * math.pi * freq * i / sr)))
            for i in range(n)
        )
        wf.writeframes(data)
    return path


class TestMusicEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = MusicEngine()
        cls.tmpdir = tempfile.mkdtemp()

    def _wav(self, name, dur=0.3):
        return make_wav(os.path.join(self.tmpdir, name), dur)

    def test_load_and_list(self):
        p = self._wav("a.wav")
        self.engine.load_track("TestA", p)
        # no crash

    def test_play_ambient(self):
        p = self._wav("b.wav")
        self.engine.load_track("TestB", p)
        self.engine.play_ambient("TestB", fade_ms=50)
        self.assertEqual(self.engine.get_current_ambient(), "TestB")

    def test_play_stinger(self):
        p = self._wav("c.wav", dur=0.2)
        self.engine.load_track("TestC", p)
        self.engine.play_stinger("TestC", fade_ms=50)
        # no crash

    def test_stop(self):
        self.engine.stop(fade_ms=50)
        self.assertIsNone(self.engine.get_current_ambient())

    def test_volume(self):
        self.engine.set_volume(0.5)
        self.assertAlmostEqual(self.engine._master, 0.5)


class TestLibrary(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Monkey-patch library paths
        import library as libmod
        libmod.LIB_DIR = self.tmpdir
        libmod.LIB_JSON = os.path.join(self.tmpdir, "library.json")
        self.lib = Library()
        self.lib._tracks = []  # clean

    def test_add_and_get(self):
        wav = make_wav(os.path.join(self.tmpdir, "src.wav"))
        t = self.lib.add_track(wav, "My Track", "City", "ambient")
        self.assertEqual(t.name, "My Track")
        found = self.lib.get_track("My Track")
        self.assertIsNotNone(found)

    def test_categories(self):
        wav = make_wav(os.path.join(self.tmpdir, "s1.wav"))
        self.lib.add_track(wav, "T1", "CatA", "ambient")
        wav2 = make_wav(os.path.join(self.tmpdir, "s2.wav"))
        self.lib.add_track(wav2, "T2", "CatB", "stinger")
        self.assertIn("CatA", self.lib.categories(kind="ambient"))
        self.assertIn("CatB", self.lib.categories(kind="stinger"))
        self.assertNotIn("CatB", self.lib.categories(kind="ambient"))

    def test_remove(self):
        wav = make_wav(os.path.join(self.tmpdir, "rem.wav"))
        self.lib.add_track(wav, "ToRemove", "X", "stinger")
        self.assertTrue(self.lib.remove_track("ToRemove"))
        self.assertIsNone(self.lib.get_track("ToRemove"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
