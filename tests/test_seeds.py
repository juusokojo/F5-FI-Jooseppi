"""Tests for one take per seed and its listening page (f5fi.seed_takes, E9). The model and Whisper are replaced by
stand-ins, so no audio model is loaded.

    .venv/bin/python -m unittest discover tests
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import f5fi  # noqa: E402

SR = 24000


def fake_generate(tts, ref, ref_text, text, nfe, speed, seed, tail_s):
    """Half a second of tone whose pitch depends on the seed, then silence."""
    t = np.arange(int(0.5 * SR)) / SR
    wave = 0.3 * np.sin(2 * np.pi * (200 + 10 * seed) * t).astype(np.float32)
    return np.concatenate([wave, np.zeros(SR // 10, np.float32)]), SR


class ParseSeedsTest(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(f5fi.parse_seeds("4-7"), [4, 5, 6, 7])
        self.assertEqual(f5fi.parse_seeds("4,6,9"), [4, 6, 9])
        self.assertEqual(f5fi.parse_seeds("4-6, 9"), [4, 5, 6, 9])
        self.assertEqual(f5fi.parse_seeds("5"), [5])
        self.assertEqual(f5fi.parse_seeds("4-5,5,4"), [4, 5])

    def test_bad(self):
        for spec in ("", "7-4", "a", "4-"):
            with self.assertRaises(ValueError, msg=spec):
                f5fi.parse_seeds(spec)


class SeedTakesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.calls = []

        def gen(*a):
            self.calls.append(a[6])  # seed
            return fake_generate(*a)

        patches = [mock.patch.object(f5fi, "_generate", side_effect=gen),
                   mock.patch.object(f5fi, "transcribe", return_value="silti palautin sen kauppaan"),
                   mock.patch.object(f5fi, "normalize_text", side_effect=lambda t: t.lower())]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def take(self, text, seeds, **kw):
        return f5fi.seed_takes(None, "ref.wav", "Viite.", text, self.dir, seeds, **kw)

    def saved(self):
        with open(os.path.join(self.dir, f5fi.SEEDS_FILE), encoding="utf-8") as f:
            return json.load(f)

    def test_one_file_per_seed(self):
        entry = self.take("Silti palautin sen kauppaan.", [4, 5, 6])
        self.assertEqual(entry["name"], "lause01")
        self.assertEqual([t["file"] for t in entry["takes"]],
                         ["lause01-s04.wav", "lause01-s05.wav", "lause01-s06.wav"])
        for t in entry["takes"]:
            self.assertTrue(os.path.exists(os.path.join(self.dir, t["file"])))
            self.assertEqual(t["whisper"], "silti palautin sen kauppaan")
            self.assertGreater(t["score"], 0.9)
        self.assertEqual(entry["model_text"], "silti palautin sen kauppaan.")
        self.assertEqual(self.calls, [4, 5, 6])

    def test_existing_takes_are_not_made_again(self):
        self.take("Silti palautin sen kauppaan.", [4, 5])
        self.calls.clear()
        entry = self.take("Silti palautin sen kauppaan.", [4, 5, 6])
        self.assertEqual(self.calls, [6])
        self.assertEqual([t["seed"] for t in entry["takes"]], [4, 5, 6])
        self.calls.clear()
        self.take("Silti palautin sen kauppaan.", [5], force=True)
        self.assertEqual(self.calls, [5])

    def test_other_settings_start_over(self):
        self.take("Silti palautin sen kauppaan.", [4, 5])
        self.calls.clear()
        entry = self.take("Silti palautin sen kauppaan.", [4], nfe=16)
        self.assertEqual(self.calls, [4])
        self.assertEqual([t["seed"] for t in entry["takes"]], [4])

    def test_sentences_share_a_folder(self):
        self.take("Silti palautin sen kauppaan.", [4])
        second = self.take("Siksi ehdin lukea koko lehden.", [4])
        self.assertEqual(second["name"], "lause02")
        again = self.take("Silti palautin sen kauppaan.", [5])
        self.assertEqual(again["name"], "lause01")
        self.assertEqual([e["name"] for e in self.saved()["lauseet"]], ["lause01", "lause02"])

    def test_given_name(self):
        entry = self.take("Silti palautin sen kauppaan.", [4], name="V2-01-s2")
        self.assertEqual(entry["takes"][0]["file"], "V2-01-s2-s04.wav")
        with self.assertRaises(ValueError):
            self.take("Toinen teksti.", [4], name="V2-01-s2")

    def test_without_whisper(self):
        entry = self.take("Silti palautin sen kauppaan.", [4], whisper=False)
        self.assertNotIn("whisper", entry["takes"][0])
        f5fi.transcribe.assert_not_called()

    def test_page(self):
        self.take("Silti <palautin> sen kauppaan.", [4, 5])
        with open(os.path.join(self.dir, f5fi.SEEDS_PAGE), encoding="utf-8") as f:
            page = f.read()
        self.assertIn('src="lause01-s04.wav"', page)
        self.assertIn('src="lause01-s05.wav"', page)
        self.assertIn('type=radio name="lause01" value="5"', page)
        self.assertIn("Silti &lt;palautin&gt; sen kauppaan.", page)
        self.assertNotIn("<palautin>", page)


if __name__ == "__main__":
    unittest.main()
