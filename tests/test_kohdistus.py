"""Tests for aligning a continuous reading to its text (scripts/kohdistus.py). No model, no audio: Whisper's words
and the loudness of the recording are made up.

    .venv/bin/python -m unittest discover tests
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import kohdistus as k  # noqa: E402

FRAME = 0.02
LOUD, QUIET, THRESHOLD = -20.0, -70.0, -45.0
WORD_S = 0.4

TEXT = [
    "Uusi naapuri",
    "Muutin Tampereelle syyskuun alussa, kun sain töitä kaupunginkirjastosta.",
    "Vuokrasin pienen kaksion vanhasta kerrostalosta.",
    "Asuntoni oli neljännessä.",
]


def reading(parts, lead=1.0, tail=1.0, closures=()):
    """Whisper-like words and frame loudness for spoken parts [(text, pause after in s)]. Each word lasts WORD_S
    and words of a part follow each other without a gap. `closures` are (word index, length): a quiet run that long
    in the middle of that word, like the closure of a double consonant."""
    words, t = [], lead
    for text, pause in parts:
        for w in text.split():
            words.append({"word": w, "start": round(t, 3), "end": round(t + WORD_S, 3)})
            t += WORD_S
        t += pause
    total = t + tail
    db = np.full(int(round(total / FRAME)), QUIET)
    for w in words:
        db[int(round(w["start"] / FRAME)):int(round(w["end"] / FRAME))] = LOUD
    for i, length in closures:
        mid = (words[i]["start"] + words[i]["end"]) / 2
        db[int(round((mid - length / 2) / FRAME)):int(round((mid + length / 2) / FRAME))] = QUIET
    return words, db


def run(parts, text=TEXT, **kw):
    words, db = reading(parts, **kw)
    return k.sentence_rows(text, words, db, THRESHOLD, FRAME), words


def by_sentence(rows):
    return {r["sentence"]: r for r in rows if r["status"] != k.EXTRA}


class AlignTest(unittest.TestCase):
    def test_identical(self):
        w = "a b c d".split()
        self.assertEqual(k.align(w, w), [0, 1, 2, 3])

    def test_repeat_uses_last_copy(self):
        self.assertEqual(k.align("x a b y".split(), "x a b a b y".split()), [0, 3, 4, 5])

    def test_unread_end(self):
        self.assertEqual(k.align("a b c d".split(), "a b".split()), [0, 1, None, None])

    def test_compound_written_as_two_words(self):
        links = k.align(["sain", "kaupunginkirjastosta", "eilen"], ["sain", "kaupungin", "kirjastosta", "eilen"])
        self.assertEqual(links[0], 0)
        self.assertIn(links[1], (1, 2))
        self.assertEqual(links[2], 3)


class ReadingTest(unittest.TestCase):
    def test_clean_reading(self):
        rows, words = run([(s, 0.5) for s in TEXT])
        self.assertEqual([r["sentence"] for r in rows], [1, 2, 3, 4])
        self.assertTrue(all(r["status"] == k.KEPT for r in rows), [r["status"] for r in rows])
        # clips start before the first word and end after the last, inside the pauses
        self.assertLess(rows[1]["start"], words[2]["start"])
        self.assertGreater(rows[1]["start"], words[1]["end"])
        self.assertGreater(rows[1]["end"], words[9]["end"])
        self.assertLessEqual(rows[1]["end"], rows[2]["start"])
        self.assertEqual(k.missing_sentences(rows, len(TEXT)), [])

    def test_false_start_left_out(self):
        rows, words = run([(TEXT[0], 0.5), ("Muutin Tampe", 0.6), (TEXT[1], 0.5), (TEXT[2], 0.5), (TEXT[3], 0.5)])
        s = by_sentence(rows)
        self.assertEqual(s[2]["status"], k.KEPT)
        retake = next(w for w in words[4:] if w["word"] == "Muutin")
        self.assertGreater(s[2]["start"], words[3]["end"])  # after the false start "Tampe"
        self.assertLess(s[2]["start"], retake["start"])
        extra = [r for r in rows if r["status"] == k.EXTRA]
        self.assertEqual(len(extra), 1)
        self.assertEqual(extra[0]["heard"], "Muutin Tampe")
        self.assertEqual(extra[0]["sentence"], 2)

    def test_whole_sentence_reread_keeps_last(self):
        rows, words = run([(TEXT[0], 0.5), (TEXT[1], 0.8), (TEXT[1], 0.5), (TEXT[2], 0.5)])
        s = by_sentence(rows)
        second = [w for w in words if w["word"] == "Muutin"][1]
        self.assertEqual(s[2]["status"], k.KEPT)
        self.assertLess(abs(s[2]["start"] - (second["start"] - k.EDGE_S)), 0.05)
        self.assertEqual(sum(r["status"] == k.EXTRA for r in rows), 1)

    def test_reading_stopped_mid_text(self):
        rows, _ = run([(TEXT[0], 0.5), (TEXT[1], 0.5)])
        self.assertEqual(sorted(by_sentence(rows)), [1, 2])
        self.assertEqual(k.missing_sentences(rows, len(TEXT)), [])

    def test_skipped_sentence_is_missing(self):
        rows, _ = run([(TEXT[0], 0.5), (TEXT[2], 0.5), (TEXT[3], 0.5)])
        self.assertNotIn(2, by_sentence(rows))
        self.assertEqual(k.missing_sentences(rows, len(TEXT)), [2])

    def test_repeated_word_flagged(self):
        rows, _ = run([(TEXT[0], 0.5), ("Muutin Tampereelle syyskuun alussa, kun sain kun sain töitä "
                                        "kaupunginkirjastosta.", 0.5), (TEXT[2], 0.5)])
        self.assertEqual(by_sentence(rows)[2]["status"], k.CHECK)

    def test_compound_split_not_flagged(self):
        rows, _ = run([(TEXT[0], 0.5), ("Muutin Tampereelle syyskuun alussa, kun sain töitä kaupungin "
                                        "kirjastosta.", 0.5), (TEXT[2], 0.5)])
        self.assertEqual(by_sentence(rows)[2]["status"], k.KEPT)

    def test_sentences_without_pause_become_one_clip(self):
        rows, words = run([(TEXT[0], 0.5), (TEXT[1], 0.0), (TEXT[2], 0.5), (TEXT[3], 0.5)])
        s = by_sentence(rows)
        self.assertEqual(sorted(s), [1, 2, 4])
        self.assertEqual(s[2]["last"], 3)
        self.assertEqual(s[2]["written"], TEXT[1] + " " + TEXT[2])
        self.assertEqual(s[2]["status"], k.KEPT)
        self.assertGreater(s[2]["end"], words[14]["end"])  # last word of sentence 3
        self.assertEqual(k.missing_sentences(rows, len(TEXT)), [])

    def test_misheard_first_and_last_word_stay_in_the_clip(self):
        # Whisper hears "Kulin" for "Kuljin" and "kaardemummaa" for "kardemummaa"
        text = ["Uusi naapuri", "Kuljin perässä tyhjin käsin.", "Siinä oli paljon kardemummaa.", "Asuntoni oli neljännessä."]
        rows, words = run([(text[0], 0.5), ("Kulin perässä tyhjin käsin.", 0.5),
                           ("Siinä oli paljon kaardemummaa.", 0.5), (text[3], 0.5)], text=text)
        s = by_sentence(rows)
        self.assertFalse(any(r["status"] == k.EXTRA for r in rows))
        self.assertLess(s[2]["start"], words[2]["start"])
        self.assertGreater(s[3]["end"], words[9]["end"])

    def test_double_consonant_closure_is_not_a_cut(self):
        # Whisper puts the start of "Vuokrasin" 0.3 s late; the 0.15 s closure inside the word must not be taken
        words, db = reading([(s, 0.5) for s in TEXT], closures=[(10, 0.15)])
        words[10] = dict(words[10], start=words[10]["start"] + 0.3)
        rows = k.sentence_rows(TEXT, words, db, THRESHOLD, FRAME)
        s = by_sentence(rows)
        self.assertLess(s[3]["start"], words[10]["start"] - 0.3)
        self.assertEqual(s[3]["status"], k.KEPT)

    def test_whisper_starts_words_inside_the_pause(self):
        # as Whisper does: the first word of the recording starts at 0.0 and a word after a pause starts where the
        # previous one ended; clips must still start EDGE_S before the voice
        words, db = reading([(TEXT[0], 0.5), (TEXT[1], 1.2), (TEXT[2], 0.5)], lead=1.0)
        voice = [w["start"] for w in words]
        words[0] = dict(words[0], start=0.0)
        words[10] = dict(words[10], start=words[9]["end"])
        s = by_sentence(k.sentence_rows(TEXT, words, db, THRESHOLD, FRAME))
        self.assertAlmostEqual(s[1]["start"], voice[0] - k.EDGE_S, delta=0.03)
        self.assertAlmostEqual(s[3]["start"], voice[10] - k.EDGE_S, delta=0.03)
        self.assertEqual([s[i]["status"] for i in (1, 2, 3)], [k.KEPT] * 3)


class ChunkTest(unittest.TestCase):
    def test_chunks_cut_in_pauses_and_cover_all(self):
        words, db = reading([(" ".join(["sana"] * 20), 0.6) for _ in range(12)])
        pieces = k.chunks(db, THRESHOLD, FRAME)
        total = len(db) * FRAME
        self.assertAlmostEqual(pieces[0][0], 0.0)
        self.assertAlmostEqual(pieces[-1][1], total)
        for (a, b), (c, _) in zip(pieces, pieces[1:]):
            self.assertAlmostEqual(b, c)
            self.assertLessEqual(b - a, k.CHUNK_S + 1e-9)
            frame = int(b / FRAME)
            self.assertEqual(db[frame], QUIET)


if __name__ == "__main__":
    unittest.main()
