"""Text normalization tests. No model, no audio.

    .venv/bin/python -m unittest discover tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import rajageminaatio as rg  # noqa: E402

HAVE_VOIKKO = rg._analyzer() is not None


@unittest.skipUnless(HAVE_VOIKKO, "Voikko puuttuu")
class InfinitiveTest(unittest.TestCase):
    def check(self, text, expected):
        self.assertEqual(rg.mark(text), expected)

    def test_infinitive_after_governor(self):
        self.check("Voisitko selittää sen vielä kerran?", "Voisitko selittääs sen vielä kerran?")
        self.check("Haluan antaa paljon.", "Haluan antaap paljon.")
        self.check("Hän haluaa selittää sen.", "Hän haluaa selittääs sen.")

    def test_one_word_between_governor_and_infinitive(self):
        self.check("Voisitko vielä selittää sen?", "Voisitko vielä selittääs sen?")

    def test_sentence_before_does_not_block(self):
        self.check("Mä en ihan tajunnu, mitä sä tarkotit. Voisitko selittää sen vielä kerran?",
                   "Mä en ihan tajunnu, mitä sä tarkotit. Voisitko selittääs sen vielä kerran?")

    def test_unambiguous_infinitive(self):
        self.check("Pitää huolehtia lapsista.", "Pitää huolehtial lapsista.")
        self.check("Ei kannata mennä kotiin.", "Ei kannatam mennäk kotiin.")

    def test_passive_connegative(self):
        self.check("Ei mennä sinne.", "Ei mennäs sinne.")

    def test_consonant_follows_next_word(self):
        self.check("Voisitko selittää tämän?", "Voisitko selittäät tämän?")
        self.check("Voisitko selittää minulle?", "Voisitko selittääm minulle?")
        self.check("Voisitko selittää kaiken?", "Voisitko selittääk kaiken?")

    def test_third_person_is_left_alone(self):
        self.check("Hän selittää sen huomenna.", "Hän selittää sen huomenna.")
        self.check("Hän antaa paljon.", "Hän antaa paljon.")

    def test_no_marking_before_vowel(self):
        self.check("Haluan selittää asian.", "Haluan selittää asian.")

    def test_no_marking_across_punctuation(self):
        self.check("Täytyy sanoa, että hyvä.", "Täytyy sanoa, että hyvä.")
        self.check("Voisitko, siis, selittää sen?", "Voisitko, siis, selittää sen?")

    def test_imperative_is_on_by_default(self):
        # E5, on since 2026-11-12; also after älä (the imperative's negative form geminates too)
        self.check("Kysy neuvoa.", "Kysyn neuvoa.")
        self.check("Älä mene sinne, vaan tule tänne.", "Älä menes sinne, vaan tulet tänne.")
        self.assertEqual(rg.mark("Mene kotiin.", enabled={"infinitive"}), "Mene kotiin.")

    def test_enabled_kinds_can_be_chosen(self):
        self.assertEqual(rg.mark("Mene kotiin.", enabled={"imperative"}), "Menek kotiin.")
        self.assertEqual(rg.mark("Älä mene.", enabled={"negative_imperative"}), "Äläm mene.")
        self.assertEqual(rg.mark("Voisitko selittää sen?", enabled=set()), "Voisitko selittää sen?")

    def test_capital_next_word(self):
        self.check("Haluan antaa Pekalle.", "Haluan antaap Pekalle.")

    def test_connegative_on_and_vowel_h_off_by_default(self):
        self.check("Tätä ei kannata tehdä yksin.", "Tätä ei kannatat tehdä yksin.")
        self.check("Ei tarvitse ymmärtää kaikkea.", "Ei tarvitse ymmärtääk kaikkea.")


@unittest.skipUnless(HAVE_VOIKKO, "Voikko puuttuu")
class ConnegativeTest(unittest.TestCase):
    """E2 in docs/aantamishavainnot.md; on since the listening test 2026-11-12."""

    def check(self, text, expected, vowel_h=False):
        self.assertEqual(rg.mark(text, enabled={"infinitive", "connegative"}, vowel_h=vowel_h), expected)

    def test_after_negation_verb(self):
        self.check("Tätä ei kannata tehdä yksin.", "Tätä ei kannatat tehdä yksin.")
        self.check("En ole nähnyt häntä.", "En olen nähnyt häntä.")
        self.check("Emme ehdi käydä kaupassa.", "Emme ehdik käydäk kaupassa.")
        self.check("Hän ei voi myöhästyä.", "Hän ei voim myöhästyä.")

    def test_connegative_does_not_stop_the_infinitive_after_it(self):
        self.check("Tietoja ei kannata syöttää palveluun.", "Tietoja ei kannatas syöttääp palveluun.")

    def test_without_negation_verb_is_left_alone(self):
        self.check("Hän saa tulla.", "Hän saa tulla.")
        self.check("Kysy kolme asiaa.", "Kysy kolme asiaa.")
        self.check("Älä mene sinne.", "Älä mene sinne.")

    def test_not_across_punctuation_or_words(self):
        self.check("Ei, kannata tehdä.", "Ei, kannata tehdä.")
        self.check("Ei vielä kannata tehdä.", "Ei vielä kannata tehdä.")


@unittest.skipUnless(HAVE_VOIKKO, "Voikko puuttuu")
class VowelHTest(unittest.TestCase):
    """E3 in docs/aantamishavainnot.md; off: the h was heard as h in the listening test 2026-11-12."""

    def test_h_before_vowel(self):
        self.assertEqual(rg.mark("Pitää ymmärtää itse.", vowel_h=True), "Pitää ymmärtääh itse.")
        self.assertEqual(rg.mark("Haluan selittää asian.", vowel_h=True), "Haluan selittääh asian.")

    def test_with_connegative(self):
        self.assertEqual(rg.mark("Ei tarvitse ymmärtää kaikkea.", enabled={"infinitive", "connegative"}, vowel_h=True),
                         "Ei tarvitseh ymmärtääk kaikkea.")

    def test_consonants_unchanged_and_third_person_left_alone(self):
        self.assertEqual(rg.mark("Voisitko selittää sen?", vowel_h=True), "Voisitko selittääs sen?")
        self.assertEqual(rg.mark("Hän selittää asian.", vowel_h=True), "Hän selittää asian.")


@unittest.skipUnless(HAVE_VOIKKO, "Voikko puuttuu")
class ListAndCompoundTest(unittest.TestCase):
    """E4, E7 and E8 in docs/aantamishavainnot.md; on since the listening test 2026-11-12."""

    def test_on_by_default(self):
        text = "Voi ehdottaa rakennetta, kirjoittaa saatetekstin pitopalveluyrittäjälle."
        self.assertEqual(rg.mark_compounds(rg.mark(text)),
                         "Voi ehdottaar rakennetta, kirjoittaas saatettekstin pitopalvelu-yrittäjälle.")
        self.assertEqual(rg.mark_compounds(rg.mark(text, list_governor=False), e_gemination=False, vowel_hyphen=False),
                         "Voi ehdottaar rakennetta, kirjoittaa saatetekstin pitopalveluyrittäjälle.")

    def test_list_governor(self):
        self.assertEqual(rg.mark("Voi ehdottaa rakennetta, kirjoittaa saatetekstin ja ideoida.", list_governor=True),
                         "Voi ehdottaar rakennetta, kirjoittaas saatetekstin ja ideoida.")
        self.assertEqual(rg.mark("Voi varata ajan, lähettää muistutuksen ja näyttää kuvia.", list_governor=True),
                         "Voi varata ajan, lähettääm muistutuksen ja näyttääk kuvia.")
        # not across a sentence end, and not without a governed infinitive before
        self.assertEqual(rg.mark("Hän voi tulla. Pekka, näyttää kuvia.", list_governor=True), "Hän voi tulla. Pekka, näyttää kuvia.")
        self.assertEqual(rg.mark("Hän tuli, näyttää kuvia.", list_governor=True), "Hän tuli, näyttää kuvia.")

    def test_compound_e_gemination(self):
        self.assertEqual(rg.mark_compounds("saatetekstin, perhetuttu, huonekalu", e_gemination=True),
                         "saatettekstin, perhettuttu, huonekkalu")
        # nukke-type and itse do not double; vowel seams are left to the hyphen option
        self.assertEqual(rg.mark_compounds("nukketeatteri, itsepalvelu, ruokaohje", e_gemination=True, vowel_hyphen=False),
                         "nukketeatteri, itsepalvelu, ruokaohje")

    def test_compound_vowel_hyphen(self):
        self.assertEqual(rg.mark_compounds("pitopalveluyrittäjä, taloyhtiö, ruoka-aine", vowel_hyphen=True),
                         "pitopalvelu-yrittäjä, talo-yhtiö, ruoka-aine")


class ColonSplitTest(unittest.TestCase):
    """E1; on since the listening test 2026-11-12."""

    @unittest.skipUnless(HAVE_VOIKKO, "Voikko puuttuu")
    def test_split(self):
        import f5fi
        self.assertEqual(f5fi.split_colon("Kysy itseltäsi yksi asia: Mitä haluan oppia?"),
                         ["Kysy itseltäsi yksi asia.", "mitä haluan oppia?"])
        self.assertEqual(f5fi.split_colon("Kello on 10:30."), ["Kello on 10:30."])
        self.assertTrue(f5fi.COLON_SPLIT)

    def test_raw_text_is_not_split(self):
        import inspect
        import f5fi
        self.assertIn("COLON_SPLIT and normalize", inspect.getsource(f5fi.synthesize))


class NormalizeTest(unittest.TestCase):
    def test_capital_umlauts_lowercased(self):
        import f5fi
        self.assertEqual(f5fi.normalize_text("Älä mene. Öljy ja Åland.", geminate=False), "älä mene. öljy ja åland.")

    @unittest.skipUnless(HAVE_VOIKKO, "Voikko puuttuu")
    def test_lower_first_is_on_by_default(self):
        import f5fi
        self.assertEqual(f5fi.normalize_text("Riittää. Tutkijat tietävät.", geminate=False), "riittää. tutkijat tietävät.")
        self.assertEqual(f5fi.normalize_text("Riittää.", geminate=False, lower=False), "Riittää.")

    @unittest.skipUnless(HAVE_VOIKKO, "Voikko puuttuu")
    def test_lower_first(self):
        import f5fi
        self.assertEqual(f5fi.lower_first("Riittää, että tietää. Tutkijat ovat samaa mieltä! Kolmas kohta."),
                         "riittää, että tietää. tutkijat ovat samaa mieltä! kolmas kohta.")
        self.assertEqual(f5fi.lower_first("Leena on yrittäjä. Helsinki on kaupunki. EU päättää."),
                         "Leena on yrittäjä. Helsinki on kaupunki. EU päättää.")
        self.assertEqual(f5fi.lower_first("Tuuli tuli järveltä. Aamulla satoi."), "tuuli tuli järveltä. aamulla satoi.")
        self.assertEqual(f5fi.lower_first("Hän sanoi: Tulen huomenna."), "hän sanoi: Tulen huomenna.")
        self.assertEqual(f5fi.normalize_text("Asiakas soitti.", geminate=False, lower=True), "asiakas soitti.")

    @unittest.skipUnless(HAVE_VOIKKO, "Voikko puuttuu")
    def test_full_normalization(self):
        import f5fi
        self.assertEqual(f5fi.normalize_text("Älä unohda sammuttaa valoja."), "älä unohdas sammuttaav valoja.")


class ScoreTest(unittest.TestCase):
    def test_extra_syllable_scores_lower(self):
        import f5fi
        self.assertEqual(f5fi.score("Äiti leipoi pullaa.", "Äiti leipoi pullaa"), 1.0)
        self.assertLess(f5fi.score("Äiti leipoi pullaa.", "Äiti leipoi pullaato."), 1.0)

    def test_digits_stand_for_number_words(self):
        import f5fi
        self.assertEqual(f5fi.score("Kirjasto on auki arkisin kahdeksasta kahdeksaan.", "Kirjasto on auki arkisin 8-8."), 1.0)
        self.assertGreater(f5fi.score("Kokous on kello kymmeneen.", "Kokous on kello 10.00."), 0.97)
        self.assertLess(f5fi.score("Kissa makasi ikkunalaudalla ja katseli lintuja.", "Kissa makasi Ikkulaa naulella."), 0.85)


if __name__ == "__main__":
    unittest.main()
