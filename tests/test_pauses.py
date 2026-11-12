"""Tests for the optional pause cap inside a line (f5fi.find_pauses, cap_pauses, E10). Made-up audio, no model.

    .venv/bin/python -m unittest discover tests
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import f5fi  # noqa: E402

SR = 24000


def line(parts):
    """Audio from [("tone" | "quiet", seconds)]. Tones are 220 Hz, as loud as speech; quiet is near silence."""
    out = []
    for kind, s in parts:
        n = int(round(s * SR))
        if kind == "tone":
            out.append(0.3 * np.sin(2 * np.pi * 220 * np.arange(n) / SR))
        else:
            out.append(np.random.default_rng(0).normal(0, 1e-4, n))
    return np.concatenate(out).astype(np.float32)


# lead 0.2 s, word, pause 0.4 s, word, pause 0.12 s, word, pause 0.06 s (a closure), word, tail 0.2 s
LINE = [("quiet", 0.2), ("tone", 0.3), ("quiet", 0.4), ("tone", 0.3), ("quiet", 0.12), ("tone", 0.3),
        ("quiet", 0.06), ("tone", 0.3), ("quiet", 0.2)]


def lengths(pauses):
    return [round(e - s, 2) for s, e in pauses]


class FindPausesTest(unittest.TestCase):
    def test_inside_only_and_long_enough(self):
        pauses = f5fi.find_pauses(line(LINE), SR)
        self.assertEqual(lengths(pauses), [0.4, 0.12])
        self.assertAlmostEqual(pauses[0][0], 0.5, delta=0.01)

    def test_empty_and_silent(self):
        self.assertEqual(f5fi.find_pauses(np.zeros(0, np.float32), SR), [])
        self.assertEqual(f5fi.find_pauses(np.zeros(SR, np.float32), SR), [])


class CapPausesTest(unittest.TestCase):
    def test_off_by_default(self):
        wave = line(LINE)
        self.assertIs(f5fi.cap_pauses(wave, SR), wave)

    def test_cap(self):
        wave = line(LINE)
        out = f5fi.cap_pauses(wave, SR, max_s=0.15)
        self.assertEqual(lengths(f5fi.find_pauses(out, SR)), [0.15, 0.12])
        self.assertAlmostEqual((len(wave) - len(out)) / SR, 0.25, delta=0.01)
        # the words themselves are kept whole
        loud = lambda w: int(np.sum(np.abs(w) > 0.05))  # noqa: E731
        self.assertAlmostEqual(loud(out), loud(wave), delta=0.01 * SR)

    def test_longest_shortened(self):
        out = f5fi.cap_pauses(line(LINE), SR, max_s=0.1, longest_s=0.25)
        self.assertEqual(lengths(f5fi.find_pauses(out, SR)), [0.25, 0.1])

    def test_longest_lengthened(self):
        out = f5fi.cap_pauses(line(LINE), SR, longest_s=0.6)
        self.assertEqual(lengths(f5fi.find_pauses(out, SR)), [0.6, 0.12])

    def test_no_pause_no_change(self):
        wave = line([("quiet", 0.2), ("tone", 0.5), ("quiet", 0.2)])
        self.assertIs(f5fi.cap_pauses(wave, SR, max_s=0.15), wave)

    def test_no_click_at_cut(self):
        wave = line([("quiet", 0.1), ("tone", 0.3), ("quiet", 0.4), ("tone", 0.3), ("quiet", 0.1)])
        out = f5fi.cap_pauses(wave, SR, max_s=0.15)
        self.assertLess(np.max(np.abs(np.diff(out))), np.max(np.abs(np.diff(wave))) + 1e-6)


class SynthesizeTest(unittest.TestCase):
    def test_synthesize_caps_when_asked(self):
        def gen(*a):
            return line(LINE), SR

        path = os.path.join(tempfile.mkdtemp(), "out.wav")
        with mock.patch.object(f5fi, "_generate", side_effect=gen):
            f5fi.synthesize(None, "ref.wav", "Viite.", "Sana sana sana sana.", path, normalize=False)
            plain = sf.read(path)[0]
            f5fi.synthesize(None, "ref.wav", "Viite.", "Sana sana sana sana.", path, normalize=False, max_pause=0.15)
            capped = sf.read(path)[0]
        self.assertEqual(lengths(f5fi.find_pauses(plain, SR)), [0.4, 0.12])
        self.assertEqual(lengths(f5fi.find_pauses(capped, SR)), [0.15, 0.12])


if __name__ == "__main__":
    unittest.main()
