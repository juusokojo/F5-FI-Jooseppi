# F5-TTS Finnish

Suomenkielinen F5-TTS-puhesynteesimalli, jota käytetään useissa projekteissa. Tavoitteena on hienosäätää malli omalla äänellä.

## Kansiot

| Kansio | Sisältö |
|---|---|
| `base/` | Alkuperäinen malli, jota ei muuteta: `model_commonvoice_fi_librivox_fi_vox_populi_fi_20250323/` (painot `model_last_20250323.safetensors`, `vocab.txt` ja mallin mukana tullut viiteäänite). |
| `base-voxcpm2/` | Vaihtoehtoinen perusmalli VoxCPM2 (Apache-2.0), katso [Vaihtoehtoinen perusmalli](#vaihtoehtoinen-perusmalli-voxcpm2). |
| `data/` | Omat äänitteet ja litteroinnit hienosäätöä varten. Alkuperäiset äänitteet tallennetaan kansioon `data/raw/`. Kansio ei kuulu versionhallintaan. |
| `docs/` | [Nauhoitusohje](docs/nauhoitusohje.md) ja [lukulauseet](docs/lukulauseet.md) oman äänen nauhoittamiseen. [Ääntämishavainnot](docs/aantamishavainnot.md) kuuntelukokeista ja ehdotetut moduulimuutokset. |
| `checkpoints/` | Hienosäädetyt mallin versiot. |
| `scripts/` | Datan valmistelu, hienosäätö ja puheen tuottaminen. |

## Ympäristö

Python 3.14 -virtuaaliympäristö on kansiossa `.venv`. Paketit ovat samoissa versioissa kuin Rooliharjoittelun `.venv-tts`:ssä. Lisäksi asennettu `mlx-whisper` on samassa versiossa kuin Rooliharjoittelun `.venv`:ssä. Kaikki paketit on lueteltu tiedostossa `requirements-lock.txt`. Ympäristön voi rakentaa uudelleen näillä komennoilla:

```bash
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
brew install libvoikko
```

`libvoikko` on suomen morfologinen jäsennin, ja sen mukana tulee suomen sanakirja. Esikäsittely käyttää sitä rajageminaation tunnistamiseen. Sen lisenssi on GPL-2.0.

Koneella ei ole FFmpegiä. Siksi `scripts/f5fi.py` lukee viiteäänitteet soundfile-kirjastolla torchaudion sijaan, joten viiteäänitteiden pitää olla WAV-muodossa. Vokooderi (charactr/vocos-mel-24khz) on ladattu valmiiksi välimuistiin `~/.cache/huggingface`, ja skripti toimii ilman verkkoyhteyttä.

## Puheen tuottaminen

```bash
.venv/bin/python scripts/speak.py "Tekstiä puheeksi." --out puhe.wav
```

Ilman `--ref`-valitsinta `speak.py` ja `read_text.py` käyttävät suositusviitettä `data/viite/v3/viite_selitys_2.wav`. Se on määritelty yhdessä paikassa, vakiossa `f5fi.DEFAULT_REF`, joten suosituksen vaihtuessa riittää muuttaa sitä. Mallin mukana tullut viite on vakiossa `f5fi.BUNDLED_REF`. Omalla viiteäänitteellä komento on tällainen: `--ref oma.wav --ref-text "Mitä viitteessä sanotaan."`. Hienosäädetyn version saa käyttöön valitsimella `--ckpt checkpoints/<tiedosto>`.

M3-Macilla yhden lyhyen lauseen tuottaminen kestää noin 20 sekuntia (MPS, 32 askelta). Valitsimella `--nfe 16` tuottaminen on noin kaksi kertaa nopeampaa.

Ohje, joka on kirjoitettu toisen projektin Claude Code -istunnolle, on tiedostossa [docs/kaytto-muissa-projekteissa.md](docs/kaytto-muissa-projekteissa.md). Muista projekteista mallia käytetään moduulin `scripts/f5fi.py` kautta:

```python
import sys; sys.path.insert(0, "/Users/jkojo22/Koodausprojektit/Kielimallit/f5-fi/scripts")
import f5fi
tts = f5fi.load_model()
f5fi.synthesize(tts, "viite.wav", "Viitteen sanat.", "Tekstiä puheeksi.", "puhe.wav")
```

Kaikki skriptit (`speak.py`, `compare_refs.py` ja `variants.py`) käyttävät samaa moduulia. Moduuli tekee F5:n oman käsittelyn lisäksi seuraavat korjaukset. Jokainen niistä on todettu kuuntelukokeella:

| Korjaus | Miksi | Valitsin `speak.py`:ssä |
|---|---|---|
| Rajageminaatio kirjoitetaan auki: "voisitko selittää sen" muuttuu muotoon "voisitko selittääs sen" | Perusmalli ei tuota rajageminaatiota itse, mutta tuottaa sen, kun kahdentuva konsonantti on kirjoitettu tekstiin. Katso tarkemmin alta. | `--raw` ohittaa esikäsittelyn |
| Kaksoispisteen kohdalta (": ") osat tuotetaan erillisinä ottoina ja liitetään 0,3 s tauolla; kellonaika "10:30" säilyy | Ilman jakoa malli ei pitänyt kaksoispisteen kohdalla taukoa. Sokkokoe 12.11.2026: jako parempi kaikissa 5 lauseessa. | `--raw` ohittaa |
| Lauseen alkukirjain muutetaan pieneksi (nimet säilyvät) | Iso alkukirjain vaihtoi lauseen ensimmäisen äänteen: "Riittää" kuului muodossa "viittää" ja "Tutkijat" muodossa "Kutkijat". Sokkokokeessa 2026-11-12 pieni alkukirjain oli parempi neljässä lauseessa seitsemästä ja huonompi yhdessä, ja Whisper kuuli alun oikein 24 otossa 24:stä (isolla 18/24). Katso [E6](docs/aantamishavainnot.md#kuuntelukoe-e2-e3-ja-e6). | `--raw` ohittaa esikäsittelyn |
| Iso Ä, Ö ja Å muutetaan pieniksi | Malli on oppinut sanan alun ison Ä:n huonosti: "Älä mene" kuului muodossa "Lämene". | `--raw` ohittaa esikäsittelyn |
| Viitteen jälkeinen tauko 600 ms (F5:n oma tauko on 50 ms) | Lauseen alku ja tauot kuulostavat luontevammilta. | `--ref-pad-ms` |
| Puheelle annetaan 0,3 s lisäaikaa, ja loppuhiljaisuus rajataan pois | F5:n kestoarvio katkaisee lyhyitä lauseita: "Kiitos avusta" kuului muodossa "Kiitos avulla". Kuuntelussa 0,3 s antoi myös luontevimman painotuksen. 0,6 s oli liikaa, koska malli täytti ajan ylimääräisellä tavulla ("pullaato"). | `--tail` (0 = F5:n oma arvio) |
| Alle 10 tavun teksteissä ("Joo.") käytetään F5:n omaa käsittelyä | Ilman lisäaikaa "Joo." kuulosti oikealta ja painottomalta. Lisäajan kanssa se kuulosti siltä, kuin lause jatkuisi. Kun F5:n oma hidastus poistettiin, tulos meni rikki. | |

**Huomio Whisperistä:** Whisper kuuli yksisanaiset repliikit väärin silloinkin, kun ne olivat oikein. Arvioi ne siksi korvakuulolta. Whisperin pisteet eivät myöskään erota lausepainoa tai intonaatiota: kahdeksan eri siemenen ottoa sai lähes aina pisteet 1,0, vaikka kuuntelussa kelpasi vain yksi.

**Korjaukset, joita moduuli ei vielä tee:** Koulutusmateriaalit-projektin kuuntelussa (10.–11.11.2026) löytyi virheitä, jotka korjaantuivat mallille annetulla kirjoitusasulla. Pieni alkukirjain ja kahdennus kieltomuodon jälkeen testattiin sokkokokeessa 12.11.2026, ja ne ovat nyt käytössä. h vokaalin edellä ("tarvitseh ymmärtää") hylättiin yleissääntönä. Toisen sokkokokeen jälkeen (12.11.2026) käyttöön otettiin myös kahdennus käskymuodon jälkeen ("kysyn neuvoa") ja luettelossa ("…, kirjoittaas saatetekstin"), kahdennus yhdyssanan sisällä ("saatettekstin"), tavuviiva yhdyssanan vokaalirajalle ("pitopalvelu-yrittäjä") sekä kaksoispisteen jako osiin. Avoimet ehdotukset ovat tiedostossa [docs/aantamishavainnot.md](docs/aantamishavainnot.md). Niiden korjaukset muut projektit tekevät tekstiin itse ([ohje](docs/kaytto-muissa-projekteissa.md#kirjoitusasukorjaukset-joita-moduuli-ei-vielä-tee)).

**Satunnaisuus:** satunnaissiemen (`--seed`) vaikuttaa painotukseen. Se voi myös lisätä tai poistaa ylimääräisen tavun: siemenellä 2 "pullaato" muuttui oikeaksi "pullaaksi". Hienoisia vaihevirheitä esiintyy satunnaisesti eri sanoissa.

### Rajageminaatio

[rajageminaatio.py](scripts/rajageminaatio.py) lisää laukaisevan sanan loppuun seuraavan sanan ensimmäisen konsonantin: "selittääs sen", "selittäät tämän", "selittääm minulle". Sanat jäsennetään Voikolla (Homebrew'n `libvoikko` ja Python-paketti `libvoikko`). Jos Voikkoa ei ole asennettu, teksti jätetään ennalleen.

Jokainen sanaluokka otetaan käyttöön vasta kuuntelukokeen jälkeen:

| Sanaluokka | Tila | Kuuntelukoe |
|---|---|---|
| 1. infinitiivi ja passiivin kieltomuoto ("ei mennä") | käytössä | 2026-11-06: selvä parannus. Toisessa kokeessa oli 7 lausetta, joissa kahdentui s, p, k, l, t, m tai j. Merkintä paransi kuutta lausetta, j:n kanssa eroa ei kuulunut, eikä mikään lause huonontunut. Merkintä paransi myös sävelkulkua ja painotusta. |
| imperatiivi ("mene kotiin", myös *älä*-sanan jälkeen: "älä unohdas sammuttaa") | käytössä (`imperative`) | 2026-11-06: "Älä mene sinne, vaan tule tänne" kuulosti merkittynä epäluontevalta. 2026-11-12 sokkokoe: merkintä parempi 5 lauseessa 6:sta, ja tuo lause oli nyt tasan. Katso [E5](docs/aantamishavainnot.md#kuuntelukoe-e1-e4-e5-e7-ja-e8). |
| *älä* itse ("älä mene" → "äläm mene") | pois päältä | 2026-11-06, ei testattu uudelleen |
| aktiivin kieltomuoto ("ei kannata syöttää" → "kannatas") | käytössä (`connegative`) | 2026-11-12 sokkokoe: merkintä parempi 3 lauseessa 6:sta, huonompi 1:ssä ("kannatat tehdä"), ei eroa 2:ssa. Koulutusmateriaaleissa "kannatas" hyväksyttiin kahdesti. Katso [E2](docs/aantamishavainnot.md#kuuntelukoe-e2-e3-ja-e6). |
| h vokaalin edellä ("ei tarvitse ymmärtää" → "tarvitseh") | pois päältä (`VOWEL_H`) | 2026-11-12 sokkokoe: parempi 1 lauseessa 7:stä, huonompi 3:ssa, koska h kuului h:na ("hikkunan", "huida"). |
| infinitiivi luettelossa pilkun tai ja-sanan jälkeen ("voi ehdottaa …, kirjoittaas saatetekstin") | käytössä (`LIST_GOVERNOR`) | 2026-11-12 sokkokoe: parempi 2 lauseessa 5:stä, huonompi 1:ssä ("ja kirjoittaar raportti"), ei eroa 2:ssa. |
| yhdyssanan sisällä e-loppuisen alkuosan jälkeen ("saatettekstin") | käytössä (`COMPOUND_E`) | 2026-11-12 sokkokoe: parempi 4 sanassa 5:stä, ei eroa 1:ssä. |
| tavuviiva yhdyssanan vokaalirajalle ("pitopalvelu-yrittäjä") | käytössä (`COMPOUND_HYPHEN`) | 2026-11-12 sokkokoe: parempi 3:ssa, ei eroa 1:ssä, yksi arvioimatta. Ilman viivaa Whisper kuuli 4 yhdyssanaa 5:stä väärin. |

Muoto "selittää" voi olla infinitiivi tai yksikön 3. persoona ("hän selittää sen"), eikä 3. persoona aiheuta kahdentumaa. Siksi tällaiset muodot merkitään vain, kun niitä edeltää verbi, jonka jälkeen tulee infinitiivi, esimerkiksi *voida*, *haluta*, *täytyä* tai *pitää*. Välissä saa olla enintään yksi sana. Merkintää ei tehdä välimerkin yli eikä vokaalin tai numeron edellä. Voikko ei tunne useimpia puhekielisiä muotoja, joten ne jäävät merkitsemättä.

Merkintää voi kokeilla ilman synteesiä:

```bash
.venv/bin/python scripts/rajageminaatio.py "Voisitko selittää sen vielä kerran?"
```

Yksikkötestit (ilman mallia ja ääntä):

```bash
.venv/bin/python -m unittest discover tests
```

### Ehdokasvalinta

```bash
.venv/bin/python scripts/speak.py "Tekstiä puheeksi." --ref viite.wav --candidates 3 --out puhe.wav
```

Valitsimella `--candidates N` lause tuotetaan N kertaa eri siemenillä. Paikallinen Whisper (`mlx-whisper`, malli large-v3-turbo) litteroi jokaisen oton, ja tekstiä lähimpänä oleva otto valitaan. Valinta poistaa ylimääräiset tavut ja kesken jääneet lopetukset. Painotusta ja vaihevirheitä se ei havaitse. Jos jokin otto vastaa tekstiä täsmälleen, loput ottoja jätetään tekemättä.

- **Alle 10 tavun tekstit** ("Joo.") tuotetaan aina yhdellä otolla, koska Whisper kuulee yksittäiset sanat väärin silloinkin, kun ne ovat oikein.
- **Puhekieli:** Whisper kirjoittaa puhekielen sanat kirjakielisinä (esimerkiksi "tajunnu" muodossa "tajunnut"). Se laskee kaikkien ottojen pisteitä yhtä paljon, joten paremmuusjärjestys säilyy.
- **Tuottamisaika** kasvaa ottojen määrän verran.

Valitsin toimii myös skripteissä `compare_refs.py` (`--candidates`) ja `variants.py` (asetus `candidates=3`). Python-koodissa se annetaan näin: `f5fi.synthesize(..., candidates=3)`. Funktio palauttaa tiedon valitusta siemenestä sekä jokaisen oton pisteet ja litteroinnin.

Kokeiden kuuntelusivut on poistettu, kun niiden tulokset otettiin käyttöön. Omia muunnelmia voi tuottaa näin:

```bash
.venv/bin/python scripts/variants.py muunnelmat.tsv --ref data/viite/v3/viite_selitys_2.wav --out data/vertailu/<kansio>
```

Tiedostossa `muunnelmat.tsv` on yksi muunnelma riviä kohden. Rivin kentät ovat nimi, teksti ja asetukset, ja ne erotetaan sarkaimella. Asetukset annetaan muodossa `tail_s=0.3 nfe=64 seed=2 ref_pad_ms=600`.

### Siemenvalinta korvalla

```bash
.venv/bin/python scripts/speak.py "Ilmiöstä käytetään nimeä metakognitiivinen laiskuus." --seeds 4-11 --out data/vertailu/<kansio>
```

Lausepaino, fokus ja luettelon sävelkulku vaihtelevat siemenen mukaan, mutta Whisper ei kuule niitä (katso [aantamishavainnot.md, kohta 8](docs/aantamishavainnot.md#8-lausepaino-ja-luettelon-intonaatio)). Valitsin `--seeds` tuottaa yhden oton jokaisella siemenellä (`4-11`, `4,6,9` tai `4-6,9`) kansioon `--out` ja kokoaa kansioon kuuntelusivun `index.html`. Sivulla valitaan jokaisesta lauseesta paras otto, ja valinnat kootaan sivun alareunaan kopioitavaksi tekstiksi. Whisperin litterointi näkyy jokaisen oton kohdalla vain huomautuksena puuttuvista tai ylimääräisistä sanoista.

- **Monta lausetta samalle sivulle:** aja komento uudelleen toisella tekstillä ja samalla kansiolla. Lauseet nimetään järjestyksessä (`lause01`, `lause02` …), tai nimen voi antaa valitsimella `--name`. Tiedostot ovat muotoa `lause01-s04.wav`.
- **Keskeytys ja lisäsiemenet:** valmiita ottoja ei tehdä uudelleen, joten ajon voi jatkaa tai siemeniä lisätä (`--seeds 12-15`). Valitsin `--force` tekee otot uudelleen. Jos viite, malli tai asetukset muuttuvat, lauseen vanhat otot jätetään pois sivulta, koska ne eivät olisi vertailukelpoisia.
- **Tiedot:** kansion `siemenet.json` sisältää jokaisen lauseen tekstin, mallille menneen tekstin, asetukset sekä jokaisen oton siemenen, keston ja Whisperin litteroinnin.
- **Pythonissa:** `f5fi.seed_takes(tts, ref, ref_text, teksti, kansio, f5fi.parse_seeds("4-11"))`, kun malli on ladattu kerran.
- `--seeds` ja `--candidates` eivät käy yhdessä: siemenvalinnassa jokainen otto säilytetään, ja valinnan tekee kuuntelija. `--no-whisper` jättää litteroinnin pois.

Yksi otto kestää 15–25 sekuntia, joten kahdeksan siementä kestää noin kolme minuuttia lausetta kohden. Kun koneessa on samaan aikaan auki muistia vieviä ohjelmia (esimerkiksi Teams, Word ja selain), mallin muisti siirtyy levylle ja otto voi kestää kymmeniä minuutteja. Sulje silloin ylimääräiset ohjelmat.

### Taukojen lyhentäminen

```bash
.venv/bin/python scripts/speak.py "Hän oli varma, että juna lähtee ajoissa." --max-pause 0.15 --out puhe.wav
```

Malli pitää pilkun kohdalla usein lähes pisteen pituisen tauon (0,22–0,38 s). Valitsin `--max-pause S` lyhentää lauseen sisäiset tauot enintään S sekuntiin, ja `--longest-pause S` asettaa lauseen pisimmän tauon täsmälleen S sekunnin pituiseksi, joko lyhentäen tai hiljaisuutta lisäten. Asetus on valinnainen eikä oletuksena päällä (E10 tiedostossa [aantamishavainnot.md](docs/aantamishavainnot.md)): kuuntelussa 0,15 sekunnin raja paransi useimpia lauseita, mutta päälauseiden välinen pilkku ("aikaa, ja aika on") ja luetteloa edeltävä pilkku ("varmana, esimerkiksi", 0,25 s) tarvitsivat pidemmän tauon.

- **Tauko** on vähintään 0,1 sekunnin hiljaisuus, joka on 40 dB lauseen voimakkainta kohtaa hiljaisempi. Lyhyemmät hiljaisuudet, kuten kaksoiskonsonantin sulkeuma, jäävät ennalleen, samoin hiljaisuus lauseen alussa ja lopussa.
- **Tauko lyhennetään keskeltä,** ja leikkauskohtiin tulee 5 ms:n häivytys, jotta leikkaus ei naksahda.
- Valitsin toimii myös siemenvalinnan kanssa (`--seeds`) ja `read_text.py`:ssä (`--max-pause`). Pythonissa: `f5fi.synthesize(..., max_pause=0.15, longest_pause=0.25)` tai valmiille äänelle `f5fi.cap_pauses(wave, sr, 0.15)`.
- Kun lause jaetaan kaksoispisteen kohdalta (E1), asetus koskee kumpaakin osaa. Kaksoispisteen tauko pysyy 0,3 sekunnissa.
- **Raja koskee myös virkkeiden välistä taukoa,** jos samassa tekstissä on useampi virke. Kokeessa "Juna oli puoli tuntia myöhässä. Siksi ehdin lukea koko lehden." ainoa tauko oli pisteen kohdalla, ja se lyheni 0,33 sekunnista 0,15 sekuntiin. Anna virkkeet siksi erikseen. `read_text.py` tekee niin itse.

## Viitenäytteet ja vertailu

```bash
.venv/bin/python scripts/prepare_refs.py "data/raw/viitenäytteet" --ext wav --out data/viite/<versio>
.venv/bin/python scripts/compare_refs.py data/viite/<versio> --out data/vertailu/<kansio>
```

`prepare_refs.py` muuntaa äänitteet (aifc, m4a tai wav) 24 kHz:n mono-WAV-muotoon ja rajaa alun ja lopun hiljaisuuden. Lyhyet naksahdukset, kuten nauhoituspainikkeen ääni, skripti ohittaa.

Skripti myös normalisoi äänitteet tasolle RMS 0,1 (−20 dBFS) niin, että huiput jäävät alle −1 dBFS:n. Tämä on tärkeää, koska F5 hiljentää tuottamansa puheen viitenäytteen tasolle aina, kun viite on tavoitetasoa hiljaisempi. Normalisointi on pelkkä vahvistus: se muuttaa voimakkuutta mutta ei sävyä. Valitsimella `--no-normalize` taso säilyy ennallaan.

Skripti ilmoittaa, jos äänite on leikkautunut, jos huiput estävät nostamasta tasoa tavoitteeseen tai jos äänitteessä on taustakohinaa. Jos kansiossa on samat äänitteet useassa muodossa, valitse käytettävä muoto valitsimella `--ext`. Jokaisen näytteen sanat kirjoitetaan samannimiseen .txt-tiedostoon.

Käytössä on versio `data/viite/v2-wav`, jonka näytteet on nauhoitettu paremmalla mikrofonilla. Ensimmäisen mikrofonin aifc-näytteet on poistettu.

`compare_refs.py` tuottaa samat kolme testilausetta jokaisella näytteellä ja tekee kuuntelusivun `<kansio>/index.html`. Sivu on paikallinen tiedosto, eikä sitä julkaista.

## Pitkän tekstin lukeminen ja lähtötaso

```bash
.venv/bin/python scripts/read_text.py data/raw/aineisto/lukeminen_1.txt --ref data/viite/v3/viite_selitys_2.wav --until-s 60 --out data/vertailu/<kansio>
```

[read_text.py](scripts/read_text.py) jakaa tekstin lauseiksi, tuottaa jokaisen lauseen erikseen ja liittää lauseet yhdeksi äänitteeksi. Lauseiden väliin tulee 0,3 sekunnin tauko ja kappaleiden väliin 0,7 sekunnin tauko. Moduulin korjaukset on hiottu yksittäisille lauseille, minkä vuoksi lauseet tuotetaan yksi kerrallaan. Ehdokasvalinta on oletuksena päällä (`--candidates 3`), ja vuorosanojen ajatusviivat jätetään pois. `--until-s 60` lopettaa sen kappaleen jälkeen, jonka aikana minuutti täyttyy. `--paragraphs N` lukee täsmälleen N ensimmäistä kappaletta, ja otsikko lasketaan yhdeksi kappaleeksi.

Kansiossa `data/vertailu/2026-11-06_lahtotaso` on perusmallin lukunäyte ennen hienosäätöä. Kappaleiden määrä, siemen ja muut asetukset ovat tiedostossa `asetukset.json`. Kun hienosäädetty malli on valmis, sama katkelma tuotetaan sillä ja samalla viitteellä (`viite_kerronta_1`) vertailua varten. Uudella suositusviitteellä `viite_selitys_2` kannattaa tehdä lisäksi oma vertailu.

```bash
.venv/bin/python scripts/read_text.py data/raw/aineisto/lukeminen_1.txt --ref data/viite/v2-wav/viite_kerronta_1.wav --paragraphs <N> --ckpt checkpoints/<tiedosto> --out data/vertailu/<kansio>
```

Kansiossa `data/vertailu/2026-11-06_v2-wav` on perusmallin vertailu kaikilla viitenäytteillä.

## Hienosäätöaineisto

```bash
.venv/bin/python scripts/prepare_dataset.py "data/raw/<kansio>/lauseet1.wav" --sarja 1 --name lauseet1
.venv/bin/python scripts/prepare_dataset.py "data/raw/<kansio>/lukeminen_1.wav" --lukeminen data/raw/aineisto/lukeminen_1.txt
.venv/bin/python scripts/prepare_dataset.py --rebuild
```

Lauseiden sarjoissa (`--sarja` tai `--text`, yksi lause riviä kohden) [prepare_dataset.py](scripts/prepare_dataset.py) pilkkoo äänitteen vähintään 0,8 sekunnin taukojen kohdalta. Paikallinen Whisper litteroi jokaisen pätkän, ja skripti yhdistää pätkän siihen lauseeseen, jota se lähimmin vastaa. Jokaisesta lauseesta säilytetään viimeinen hyvä otto, koska virheen jälkeen lause luetaan uudelleen. Keskeneräiset ja uusitut otot sekä pätkät, jotka eivät vastaa mitään lausetta, hylätään. Säilytetyt pätkät normalisoidaan samalla tavalla kuin viitenäytteet.

Tulokset tallentuvat kansioon `data/aineisto/`:

| Tiedosto | Sisältö |
|---|---|
| `wavs/<nimi>_NN.wav` | Säilytetyt pätkät. NN on lauseen numero. Pitkässä luennassa numero on virkkeen järjestysnumero koko tekstissä (`lukeminen_1_012.wav`). |
| `<nimi>.tsv` | Jokainen pätkä: aika, lause, Whisperin litterointi, pisteet ja tila (käytössä, käytössä mutta tarkista, käytössä mutta tarkista raja, keskeneräinen, uusittu, ylimääräinen tai ei vastaa lausetta) |
| `<nimi>.sanat.json` | Pitkän luennan Whisper-litterointi sanakohtaisine aikoineen. Litterointi käytetään uudelleen, kun skripti ajetaan samalle äänitteelle uudestaan. |
| `<nimi>.html` | Tarkistussivu, jolla jokaisen pätkän voi kuunnella. Hylätyt pätkät tallentuvat kansioon `hylatyt/`. Sarjojen 1–4 hylätyt pätkät on poistettu tarkistuksen jälkeen. |
| `metadata.csv` | F5:n harjoitusdatan lähtötiedosto, joka kootaan kaikista .tsv-tiedostoista. Tekstit kulkevat saman esikäsittelyn läpi kuin synteesissä (rajageminaatio, pienet Ä ja Ö sekä pieni alkukirjain). Kun esikäsittely muuttuu, aja `prepare_dataset.py --rebuild`. |

### Pitkä luenta

Valitsimella `--lukeminen` pitkä luenta kohdistetaan tekstiin virke kerrallaan ([kohdistus.py](scripts/kohdistus.py)). Luennassa virkkeiden väliset tauot ovat lyhyitä (0,3–1 s), joten pelkät tauot eivät riitä virkkeiden erottamiseen. Kohdistus toimii näin:

1. Äänite jaetaan taukojen kohdalta enintään 28 sekunnin paloihin. Whisper litteroi palat ja merkitsee jokaiselle sanalle alku- ja loppuajan.
2. Kuullut sanat kohdistetaan tekstin sanoihin. Jos virke on luettu uudelleen takeltelun jälkeen, käyttöön otetaan viimeinen otto. Aiempi otto ja kesken jääneet aloitukset merkitään tilaan *ylimääräinen*, ja ne voi kuunnella tarkistussivulla.
3. Leike leikataan virkkeen ensimmäistä ja viimeistä sanaa ympäröivästä tauosta, joka etsitään äänen voimakkuudesta. Whisperin aikaleimoja ei käytetä suoraan, koska Whisper aloittaa sanan usein selvästi ennen puhetta. Leikkeen kumpaankin päähän jää 0,2 sekuntia hiljaisuutta. Tauoksi kelpaa vähintään 0,25 sekunnin hiljaisuus. Lyhyempi hiljaisuus voi olla kaksoiskonsonantin (kk, tt) sulkeuma sanan keskellä.
4. Jos virkkeiden välissä ei ole taukoa ("On. Ainakin viisi."), virkkeet yhdistetään yhdeksi leikkeeksi, jonka pituus on enintään 20 sekuntia. Leikkeen nimi tulee ensimmäisestä virkkeestä.
5. Virke merkitään tarkistettavaksi, jos Whisperin litterointi poikkeaa tekstistä tai jos virkkeen sisällä on toistettu sana. Virke merkitään tilaan *tarkista raja*, jos sen ja naapurivirkkeen välistä ei löytynyt selvää taukoa. Kun Whisper kirjoittaa yhdyssanan kahtena sanana ("kaupungin kirjastosta"), virkettä ei merkitä tarkistettavaksi.

Lukemisen voi lopettaa kesken. Jatka silloin uuteen tiedostoon, esimerkiksi `lukeminen_1b.wav`, ja aja se samalla tekstillä. Skripti löytää luetut virkkeet itse, ja puuttuviksi ilmoitetaan vain ne virkkeet, jotka jäivät väliin luetun alueen sisällä. Kokonaisen tallenteen merkitsee kuunnelluksi komennolla `--approve lukeminen_1`.

Kohdistusta on testattu yksikkötesteillä (`tests/test_kohdistus.py`) ja koeäänitteellä, joka koottiin lähtötason F5-lauseista. Koeäänitteeseen lisättiin keskeytynyt aloitus ja kahdesti luettu virke. Kaikki 12 virkettä löytyivät, uusitusta virkkeestä valittiin viimeinen otto, ja jokaisen leikkeen alussa ja lopussa on hiljaisuutta.

Ensimmäinen oikea luenta (`lukeminen_1`, 10 min, 2026-11-10) paljasti kaksi virhettä, jotka on nyt korjattu. Ensinnäkin sana, jonka Whisper kuuli kokonaan väärin virkkeen alussa tai lopussa ("Kulin" sanasta "Kuljin"), jäi leikkeen ulkopuolelle. Nyt väärin kuultu sana linkitetään paikkaansa tekstissä. Toiseksi ilman taukoa luetut vuorosanat merkittiin rajaltaan epävarmoiksi, ja nyt ne yhdistetään yhdeksi leikkeeksi. Korjausten jälkeen 166 virkettä 169:stä on käytössä, 19 on merkitty tarkistettaviksi, ja ylimääräisiä pätkiä on 3 (kaksi uusittua virkettä ja yksi kesken jäänyt aloitus). Virke 88 puuttuu äänitteestä.

### Pätkien korjaaminen

Jos tauko jää liian lyhyeksi ja kaksi peräkkäistä lausetta päätyy samaan pätkään, skripti jakaa pätkän lauseiden välisen lyhyemmän tauon kohdalta. Tauon pitää olla vähintään 0,2 sekuntia, ja kummankin puolen pitää vastata omaa lausettaan.

Epäselvän pätkän voi hylätä käsin. Silloin pätkä siirretään kansioon `hylatyt/` ja `metadata.csv` kootaan uudelleen:

```bash
.venv/bin/python scripts/prepare_dataset.py --drop lauseet1_07 lauseet1_17
```

Pätkän tekstiksi tulee kirjoitettu lause. Jos Whisperin litterointi poikkeaa siitä hieman, pätkä säilytetään mutta merkitään tarkistettavaksi. Jos sanoit lauseen toisin kuin se on kirjoitettu, korjaa teksti vastaamaan puhetta:

```bash
.venv/bin/python scripts/prepare_dataset.py --set-text lauseet3_03 "Miksi kukaan ei ole kertonut minulle tästä aiemmin?"
```

Kun tarkistettavaksi merkityt pätkät kuulostavat oikeilta, merkitse ne kuunnelluiksi. Voit antaa joko koko äänitteen tai yksittäisen pätkän:

```bash
.venv/bin/python scripts/prepare_dataset.py --approve lauseet4
.venv/bin/python scripts/prepare_dataset.py --approve lauseet4_06
```

Puhekielisissä lauseissa (sarja 4) lähes jokainen pätkä merkitään tarkistettavaksi, koska Whisper kirjoittaa puhekielen kirjakieleksi ("mennääks" muuttuu muotoon "mennäänkö"). Kuuntelussa sarjan 4 kaikki tällaiset pätkät olivat oikein.

Whisper kirjoittaa luvut numeroina ("kello 10.00"). Pisteytys tulkitsee numerot niiksi lukusanoiksi, joiden kohdalla ne ovat. Siksi kesken jäänyttä lukua ei havaita.

F5:n valmistelutyökalu (`f5_tts.train.datasets.prepare_csv_wavs`) etsii sanastoa F5:n omasta asennuskansiosta. Sille pitää antaa suomenkielisen perusmallin `vocab.txt`. Aineiston merkit sisältyvät perusmallin sanastoon, joten hienosäätö voi jatkaa suoraan perusmallista.

## Mallin tiedot

- Arkkitehtuuri: `F5TTS_v1_Base`
- Hienosäädetty suomeksi aineistoilla Common Voice, LibriVox ja VoxPopuli (2025-03-23).
- Lähde: [AsmoKoskinen/F5-TTS_Finnish_Model](https://huggingface.co/AsmoKoskinen/F5-TTS_Finnish_Model), hienosäädetty perusmallista [SWivid/F5-TTS](https://huggingface.co/SWivid/F5-TTS).
- Lisenssi: molempien painot on julkaistu lisenssillä CC BY-NC 4.0. Perusmallin rajoite johtuu koulutusaineistosta Emilia. F5-TTS:n koodi ja Vocos-vokooderi ovat MIT-lisenssin alaisia. Ei-kaupallinen käyttö on sallittua myös verkossa, kun tekijät ja lisenssi mainitaan. Hienosäädetty checkpoint on muokattu versio, joten sitä koskee sama lisenssi. Mallin tuottaman puheen kaupallinen käyttö on harmaa alue.
- Mallin mukana tullut viiteäänite `AsmoKoskinenRef_v1.wav` on oikean ihmisen ääni, eikä sille ole erillistä lupaa. Käytä muille jaettavaan aineistoon omaa viitettä.

## Vaihtoehtoinen perusmalli: VoxCPM2

[openbmb/VoxCPM2](https://huggingface.co/openbmb/VoxCPM2) on tarkoitettu tilanteisiin, joissa tarvitaan sallivampi lisenssi. Painot ja koodi on julkaistu lisenssillä Apache-2.0, joka sallii myös kaupallisen käytön. Malli tukee suomea ilman kielitunnistetta. Hienosäätöön on valmiit skriptit (kokonainen hienosäätö ja LoRA), ja mallikortin mukaan 5–10 minuuttia ääntä riittää. Mallikortti kieltää käyttämästä toisen ihmisen ääntä luvatta.

Kokeilu 2026-11-06 osoitti, että mallia voidaan käyttää, mutta se on tälle koneelle liian raskas. Siksi PoC-vaihe tehdään F5:llä, ja VoxCPM2 otetaan käyttöön GPU-palvelimella, kun laajempaa lisenssiä tarvitaan.

- **Sijainti:** painot ovat kansiossa `base-voxcpm2/VoxCPM2/` (5 Gt), ja ympäristö on `.venv-voxcpm` (voxcpm 2.0.3). Ympäristö on erillinen, jotta F5:n paketit pysyvät ennallaan.
- **Nopeus M3-Macilla (16 Gt):** MPS ei tue bfloat16:ta, joten malli toimii float32-muodossa ja vie lähes koko muistin. Lauseeseen kuluu 1,5–5 minuuttia. Lähtötason katkelma (63 s ääntä) vei 31 minuuttia, kun F5:llä yksi lause kestää noin 20 sekuntia.
- **Laatu ilman esikäsittelyä ja ehdokasvalintaa:** Whisper kuuli 8 lausetta 12:sta täsmälleen oikein. Kolmen lauseen alkuun tuli ylimääräisiä sanoja ("Autta uusi naapuri"), kun viite annettiin myös jatkettavaksi (`prompt_wav_path` + `prompt_text`). Puhetempo on F5:tä nopeampi. Ääni tuotetaan 48 kHz:n näytteenottotaajuudella.
- **Vertailu:** [voxcpm_read.py](scripts/voxcpm_read.py) lukee saman katkelman, viitteen ja tauot F5:n lähtötason tiedostosta `asetukset.json`. Kuuntelusivu on `data/vertailu/2026-11-06_voxcpm2_lahtotaso/index.html`. Kansiossa `lauseet_pelkka_viite/` ovat ne neljä ongelmalausetta uudelleen tuotettuina ilman jatkotilaa, pelkällä `reference_wav_path`-viitteellä. Ylimääräiset alut katosivat, mutta tempo nopeutui entisestään: lause "Muuttoauto tuli pihaan lauantaiaamuna kahdeksalta" kesti 2,6 s, ja Whisper kuuli sen muodossa "Mut auto tuli pihaan…". Kumpaakaan tilaa ei ole vielä kuunneltu.
- **Käyttöönotto myöhemmin:** äänitteet, aineisto, viitenäytteet ja kuuntelutyötapa siirtyvät sellaisinaan. `f5fi.py`:n korjaukset on viritetty F5:lle, joten ne kuunnellaan uudelleen. Käyttöliittymä (`load_model`, `synthesize`) pidetään ennallaan, jolloin muihin projekteihin ei tarvitse koskea. Kansio `base/` pysyy paikallaan Rooliharjoittelun symbolisen linkin vuoksi.

## Projektit, jotka käyttävät mallia

- **Rooliharjoittelu:** `Rooliharjoittelu/models/f5-fi` on symbolinen linkki kansioon `base/`. Projektin `tools/voice_compare.py` käyttää mallia linkin kautta. Älä siirrä tai nimeä `base/`-kansiota uudelleen, ellet päivitä linkkiä.
