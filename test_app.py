"""
test_app.py -- smoke tests for audio_engine and library
"""
import os
import sys
import struct
import wave
import math
import tempfile
import shutil
import time
import unittest

os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["SDL_VIDEODRIVER"] = "dummy"

sys.path.insert(0, os.path.dirname(__file__))

from audio_engine import MusicEngine
from library import Library, Track, LIB_DIR, LIB_JSON


def make_wav(path: str, duration: float = 0.5, freq: int = 440) -> str:
    sr = 8000
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

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _wav(self, name, dur=0.3):
        return make_wav(os.path.join(self.tmpdir, name), dur)

    def test_load_and_list(self):
        p = self._wav("a.wav")
        self.engine.load_track("TestA", p)
        # no crash

    def test_play_ambient(self):
        p = self._wav("b.wav")
        self.engine.load_track("TestB", p)
        self.engine.set_ambient_crossfade(50)
        self.engine.play_ambient("TestB")
        self.assertEqual(self.engine.get_current_ambient(), "TestB")

    def test_play_stinger(self):
        p = self._wav("c.wav", dur=0.2)
        self.engine.load_track("TestC", p)
        self.engine.set_stinger_fade_in(50)
        self.engine.play_stinger("TestC")
        # no crash

    def test_background_warmup(self):
        p = self._wav("warm.wav")
        self.engine.load_track("WarmTrack", p)
        self.engine.warmup_tracks(["WarmTrack"])

        for _ in range(20):
            if "WarmTrack" in self.engine._sounds:
                break
            time.sleep(0.02)

        self.assertIn("WarmTrack", self.engine._sounds)

    def test_stop(self):
        self.engine.set_stop_fade(50)
        self.engine.stop_all()
        self.assertIsNone(self.engine.get_current_ambient())

    def test_restore_previous_ambient_after_stinger_stop(self):
        ambient = self._wav("ambient.wav", dur=0.6)
        stinger = self._wav("stinger.wav", dur=0.2)
        self.engine.load_track("AmbientRestore", ambient)
        self.engine.load_track("StingerRestore", stinger)
        self.engine.set_ambient_crossfade(20)
        self.engine.set_ambient_duck_out(20)
        self.engine.set_ambient_restore_in(20)
        self.engine.set_stinger_fade_in(20)
        self.engine.set_stinger_fade_out(20)
        self.engine.set_stop_fade(20)

        self.engine.play_ambient("AmbientRestore")
        time.sleep(0.05)
        self.engine.play_stinger("StingerRestore")
        time.sleep(0.05)
        self.engine.stop_stinger()
        time.sleep(0.1)

        self.assertEqual(self.engine.get_current_ambient(), "AmbientRestore")


class TestLibrary(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Monkey-patch library paths
        import library as libmod
        libmod.LIB_DIR = self.tmpdir
        libmod.LIB_JSON = os.path.join(self.tmpdir, "library.json")
        self.lib = Library()
        self.lib._tracks = []  # clean

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

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
