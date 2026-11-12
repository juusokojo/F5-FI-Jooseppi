"""Boundary gemination (rajageminaatio) marked in text for F5-TTS Finnish.

Some Finnish forms end in an unwritten consonant: before a word that starts with a consonant, that consonant is
doubled across the word boundary ("selittää sen" is said "selittääs sen"). The base model does not produce it, but
it does when the doubled consonant is written into the text, so the consonant of the next word is added to the
end of the triggering word.

Each kind of trigger is switched on only after a listening test showed that marking it helps:

- infinitive (on): 1st infinitive, "selittää sen" -> "selittääs sen". Listening test 2026-11-06: clearly better.
  Second test with 7 lines (s, p, k, l, t, m, j): marked better in 6, no difference in 1 (j), worse in none.
- imperative, negative_imperative (off): "mene kotiin", "älä mene". Marking made "Älä mene sinne, vaan tule
  tänne" sound unnatural; the unmarked line was already right.
- connegative (on): active connegative after a negation verb,
  "ei kannata syöttää" -> "ei kannatas syöttää". Voikko analyzes the form as a 2nd person imperative, so it is told
  apart by the negation verb (ei, en, et, emme, ette, eivät) right before it. Blind listening test 2026-11-12
  (docs/aantamishavainnot.md E2): marked better in 3 of 6, worse in 1 ("kannatat tehdä"), no difference in 2.

vowel_h (off, E3): before a word starting with a vowel the gemination is a glottal stop
("ei tarvitseʔ ymmärtää"). Written as h ("tarvitseh ymmärtää") it was heard right in some lines; an apostrophe,
comma, dash or k were not. Blind listening test 2026-11-12: better in 1 of 7, worse in 3 (the h was heard as h:
"hikkunan", "huida"), so it is not used as a rule.

Off until a listening test (docs/aantamishavainnot.md):
- LIST_GOVERNOR (E4): an -aa/-ää infinitive right after a comma or ja/tai/sekä counts as governed when an earlier
  governed infinitive is in the same sentence ("voi ehdottaa rakennetta, kirjoittaa saatetekstin" -> kirjoittaas).
- mark_compounds (E7, E8): inside compounds (Voikko STRUCTURE), gemination after an e-ending first part of the
  perhe/huone type ("saatetekstin" -> "saatettekstin"), and a hyphen where a part ending in a vowel meets one
  starting with a vowel ("pitopalveluyrittäjä" -> "pitopalvelu-yrittäjä").

No marking across punctuation (a comma means a pause) or before a digit, nor before a vowel unless vowel_h. Forms Voikko does not know,
such as most colloquial ones, are left alone.

Voikko (Homebrew libvoikko + the libvoikko Python binding) analyzes the words. Without it the text is returned as is.
"""
import re

ENABLED = {"infinitive", "connegative"}
VOWEL_H = False
LIST_GOVERNOR = False
COMPOUND_E = False
COMPOUND_HYPHEN = False
LIST_JOINERS = {"ja", "tai", "sekä"}
SENTENCE_END = re.compile(r"[.!?;:]")
VOWELS = set("aeiouyäöå")

# Verbs followed by a 1st infinitive. They decide whether an -aa/-ää form ("selittää") is an infinitive
# ("voisitko selittää sen") or 3rd person singular ("hän selittää sen"), which does not trigger.
INFINITIVE_GOVERNORS = {
    "voida", "haluta", "tahtoa", "täytyä", "pitää", "tarvita", "osata", "aikoa", "yrittää", "alkaa", "jaksaa",
    "kannattaa", "viitsiä", "uskaltaa", "kehdata", "saada", "unohtaa", "muistaa", "päättää", "luvata", "toivoa",
    "tykätä", "rakastaa", "inhota", "pelätä", "ehtiä", "mahtaa", "taitaa", "tulla", "kuulua", "auttaa", "antaa",
    "käskeä", "pyytää", "kieltää", "sallia", "suunnitella", "harkita", "vihata",
}
MAX_GAP = 1  # words allowed between the governor and the infinitive ("voisitko vielä selittää sen")

CONSONANTS = set("bcdfghjklmnpqrsštvwxzž")
WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")

_voikko = None


def _analyzer():
    global _voikko
    if _voikko is None:
        try:
            import libvoikko
            libvoikko.Voikko.setLibrarySearchPath("/opt/homebrew/lib")
            _voikko = libvoikko.Voikko("fi")
        except Exception as e:  # missing library or dictionary: no marking
            print(f"rajageminaatio: Voikko ei käytettävissä ({e}); teksti jätetään ennalleen")
            _voikko = False
    return _voikko or None


def _kind(analyses):
    """Trigger kind of a word if every analysis agrees it triggers, 'maybe_infinitive' if it can be an infinitive
    or 3rd person singular, else None."""
    if not analyses:
        return None
    kinds = set()
    for a in analyses:
        mood = a.get("MOOD")
        if a.get("CLASS") == "kieltosana" and mood == "imperative":
            kinds.add("negative_imperative")
        elif a.get("CLASS") != "teonsana":
            kinds.add(None)
        elif mood == "A-infinitive":
            kinds.add("infinitive")
        elif mood == "indicative" and a.get("PERSON") == "4" and a.get("NEGATIVE") == "true":
            kinds.add("infinitive")  # passive connegative "ei mennä" is written and said like the infinitive
        elif mood == "imperative" and a.get("PERSON") == "2" and a.get("NUMBER") == "singular":
            kinds.add("imperative")
        elif mood == "indicative" and a.get("PERSON") == "3" and a.get("NUMBER") == "singular":
            kinds.add("third_person")
        else:
            kinds.add(None)
    if kinds == {"infinitive", "third_person"}:
        return "maybe_infinitive"
    return kinds.pop() if len(kinds) == 1 else None


def _is_negation(analyses):
    """Negation verb in the indicative (ei, en, et, emme, ette, eivät), not the imperative älä."""
    return any(a.get("CLASS") == "kieltosana" and a.get("MOOD") == "indicative" for a in analyses)


def _can_be_connegative(analyses):
    """Active connegative ("kannata", "ole", "tarvitse"): Voikko gives it as a 2nd person singular imperative."""
    return any(a.get("CLASS") == "teonsana" and a.get("MOOD") == "imperative" and a.get("PERSON") == "2"
               and a.get("NUMBER") == "singular" for a in analyses)


def _is_governor(analyses):
    return any(a.get("CLASS") == "teonsana" and a.get("BASEFORM") in INFINITIVE_GOVERNORS for a in analyses)


def _governed(text, words, analyses, i):
    """True if a governor verb comes within MAX_GAP words before word i, with no punctuation in between."""
    for j in range(i - 1, max(-1, i - 2 - MAX_GAP), -1):
        if not text[words[j].end():words[j + 1].start()].isspace():
            return False
        if _is_governor(analyses[j]):
            return True
    return False


def _in_infinitive_list(text, words, analyses, i):
    """Word i follows a comma or ja/tai/sekä, and an earlier word in the same sentence is a governed infinitive."""
    sep = text[words[i - 1].end():words[i].start()] if i > 0 else ""
    if not (sep.strip() == "," or (sep.isspace() and words[i - 1].group().lower() in LIST_JOINERS)):
        return False
    for j in range(i - 1, max(-1, i - 13), -1):
        if SENTENCE_END.search(text[words[j].end():words[j + 1].start()]):
            return False
        k = _kind(analyses[j])
        if k == "infinitive" or (k == "maybe_infinitive" and _governed(text, words, analyses, j)):
            return True
    return False


def mark(text, enabled=None, vowel_h=None, list_governor=None):
    """Return text with boundary gemination written out for the enabled trigger kinds.

    vowel_h: before a word starting with a vowel, write h ("tarvitseh ymmärtää"). Default VOWEL_H.
    """
    enabled = ENABLED if enabled is None else enabled
    vowel_h = VOWEL_H if vowel_h is None else vowel_h
    list_governor = LIST_GOVERNOR if list_governor is None else list_governor
    v = _analyzer()
    if v is None or not enabled:
        return text
    words = list(WORD.finditer(text))
    analyses = [v.analyze(m.group()) for m in words]
    out, pos = [], 0
    for i, m in enumerate(words[:-1]):
        nxt = words[i + 1]
        between = text[m.end():nxt.start()]
        first = nxt.group()[0].lower()
        if not between.isspace():
            continue
        if first in CONSONANTS:
            added = first
        elif first in VOWELS and vowel_h:
            added = "h"
        else:
            continue
        kind = _kind(analyses[i])
        if (i > 0 and text[words[i - 1].end():m.start()].isspace() and _is_negation(analyses[i - 1])
                and _can_be_connegative(analyses[i])):
            kind = "connegative"
        elif kind == "maybe_infinitive":
            governed = _governed(text, words, analyses, i) or (
                list_governor and _in_infinitive_list(text, words, analyses, i))
            kind = "infinitive" if governed else None
        if kind in enabled:
            out.append(text[pos:m.end()] + added)
            pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def _boundaries(analyses):
    """Character offsets where a compound part starts (not 0), common to all analyses; from Voikko STRUCTURE."""
    common = None
    for a in analyses:
        pos, cuts = 0, set()
        for ch in a.get("STRUCTURE") or "":
            if ch == "=":
                if pos:
                    cuts.add(pos)
            else:
                pos += 1
        common = cuts if common is None else common & cuts
    return sorted(common or ())


def _geminating_e(part, v):
    """Part ends in -e and is a perhe/huone-type noun (partitive -tta/-ttä), which doubles the next consonant."""
    p = part.lower()
    if not p.endswith("e"):
        return False
    pv = p + ("tta" if any(c in p for c in "aou") else "ttä")
    return any(a.get("BASEFORM") == p and a.get("SIJAMUOTO") == "osanto" for a in v.analyze(pv))


def mark_compounds(text, e_gemination=None, vowel_hyphen=None):
    """Inside compound words: gemination after perhe-type parts (E7) and a hyphen at a vowel-vowel seam (E8)."""
    e_gemination = COMPOUND_E if e_gemination is None else e_gemination
    vowel_hyphen = COMPOUND_HYPHEN if vowel_hyphen is None else vowel_hyphen
    v = _analyzer()
    if v is None or not (e_gemination or vowel_hyphen):
        return text
    out, pos = [], 0
    for m in WORD.finditer(text):
        word = m.group()
        inserts = []
        for b in _boundaries(v.analyze(word)):
            left, first = word[:b], word[b].lower()
            start = max([0] + [c for c in _boundaries(v.analyze(word)) if c < b])
            if e_gemination and first in CONSONANTS and _geminating_e(word[start:b], v):
                inserts.append((b, first))
            elif vowel_hyphen and left[-1].lower() in VOWELS and first in VOWELS and left[-1] != "-":
                inserts.append((b, "-"))
        if inserts:
            for b, s in reversed(inserts):
                word = word[:b] + s + word[b:]
            out.append(text[pos:m.start()] + word)
            pos = m.end()
    out.append(text[pos:])
    return "".join(out)


if __name__ == "__main__":
    import sys
    for line in sys.argv[1:] or sys.stdin:
        print(mark(line.rstrip("\n")))
