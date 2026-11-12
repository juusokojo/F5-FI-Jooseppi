# F5-fi: käyttö muissa projekteissa

Tämä ohje on tarkoitettu Claude Code -istunnolle, joka tuottaa toisessa projektissa suomenkielistä puhetta käyttäjän äänellä. Ohje on päivitetty 2026-11-12.

## Tilanne

- Malli on F5-TTS Finnishin perusmalli, jota **ei ole vielä hienosäädetty**. Kansiossa `checkpoints/` ei ole vielä mitään. Käyttäjän ääni tulee lyhyestä viitenäytteestä, jota malli matkii.
- Kielen laatu on hyvä. Heikkouksia ovat tasainen eläytyminen ja se, että äänen väri ei ole aivan käyttäjän oma.
- Moduuli `scripts/f5fi.py` korjaa tekstiä ennen synteesiä ja säätää F5:n omaa käsittelyä. Korjaukset on hyväksytty kuuntelukokeissa, ja ne ovat oletuksena päällä. Niitä ei tarvitse eikä pidä tehdä itse.
- Kuuntelussa on löytynyt virheitä, joita moduuli ei vielä korjaa (moduuli korjaa 12.11.2026 alkaen myös käskymuodon, luettelon ja yhdyssanojen kahdennukset, yhdyssanan vokaalirajan ja kaksoispisteen tauon). Ne korjataan mallille annettavassa tekstissä, katso [Kirjoitusasukorjaukset, joita moduuli ei vielä tee](#kirjoitusasukorjaukset-joita-moduuli-ei-vielä-tee). Havainnot perusteluineen ovat tiedostossa `$F5/docs/aantamishavainnot.md`.

## Säännöt

1. **Älä kopioi mallia, Python-ympäristöä tai skriptejä omaan projektiisi.** Viittaa niihin absoluuttisilla poluilla. Kopio jäisi jälkeen, kun malli hienosäädetään.
2. **Älä muokkaa kansiota `/Users/jkojo22/Koodausprojektit/Kielimallit/f5-fi`.** Jos tarvitset muutoksen, kerro siitä käyttäjälle. Muutokset tehdään f5-fi-projektin omassa istunnossa ja testataan kuuntelemalla.
3. **Ääni ja malli pysyvät käyttäjän koneella.** Älä julkaise tuotettua puhetta, viitenäytteitä tai kuuntelusivuja verkkoon, älä myöskään Artifactina. Perusmallin lisenssi on CC BY-NC, joten kaupallinen käyttö ei ole sallittua.
4. **Kuuntelu ratkaisee.** Pyydä käyttäjää kuuntelemaan tulos. Whisperin pisteet kertovat vain, puuttuuko sanoja tai onko niitä liikaa. Painotusta, sävyä, intonaatiota tai yksisanaisia repliikkejä ne eivät arvioi: kun samasta lauseesta tehtiin kahdeksan ottoa eri siemenillä, lähes kaikkien pisteet olivat 1,0, vaikka käyttäjä kelpuutti niistä vain yhden.
5. **Kysy ennen kuin asennat mitään** f5-fi:n ympäristöön tai omaan projektiisi.

## Polut ja suositellut asetukset

```
F5=/Users/jkojo22/Koodausprojektit/Kielimallit/f5-fi
PY=$F5/.venv/bin/python                              # aja aina tällä, -I-valitsimen kanssa
```

- **Viite:** jätä viite valitsematta, niin käytössä on aina suositeltu viite. Skriptit `speak.py` ja `read_text.py` käyttävät sitä, kun `--ref` puuttuu, ja Pythonissa se on vakiossa `f5fi.DEFAULT_REF`. Älä kirjoita viitteen polkua omaan koodiin, koska suositus voi vaihtua. Nykyinen suositus on `viite_selitys_2` (kansio `data/viite/v3/`, eläytyen luettu selittävä teksti). Se valittiin 19 viitteen joukosta kuuntelemalla, kun kaikilla luettiin sama pitkän tekstin katkelma (`data/vertailu/2026-11-10_viitteet_v3`). Edellinen suositus oli `data/viite/v2-wav/viite_kerronta_1`. Muut viitteet ovat samassa kansiossa: aiheet jannite, juhla, kirjat, lumi, rengas ja selitys, ja jokaisesta otot 1 (hillitysti), 2 (eläytyen) ja 3 (vähän liioitellen). F5 kopioi viitteestä tempon ja sävyn, joten viite määrää luennan tyylin.
- **Ehdokasvalinta:** `--candidates 3` tekee kolme ottoa ja valitsee sen, jonka Whisper kuulee lähimpänä tekstiä. Se on hitaampaa, mutta se karsii ylimääräiset tavut ja katkenneet loput.
- Muut asetukset pidetään oletuksina: nfe 32, siemen 1, viitteen jälkeinen tauko 600 ms ja 0,3 s lisäaikaa lauseen loppuun. Ne on valittu kuuntelemalla.

## Lyhyt teksti: yksi lause tai repliikki

```bash
$PY -I $F5/scripts/speak.py "Tekstiä puheeksi." --candidates 3 --out /polku/puhe.wav
```

## Pitkä teksti: kappaleita tai kokonainen teksti

```bash
$PY -I $F5/scripts/read_text.py /polku/teksti.txt --out /polku/kansio
```

Skripti jakaa tekstin lauseiksi ja tuottaa jokaisen erikseen, koska korjaukset on hiottu yksittäisille lauseille. Sitten se liittää lauseet yhteen niin, että lauseiden väliin tulee 0,3 sekunnin tauko ja kappaleiden väliin 0,7 sekunnin tauko. Kappaleet erotetaan toisistaan tyhjällä rivillä. Vuorosanojen ajatusviivat (`– `) jätetään pois. Tulokset tallentuvat näin:

- `kansio/lukeminen.wav` on koko teksti.
- `kansio/lauseet/` sisältää lauseet erillisinä tiedostoina.
- `kansio/asetukset.json` sisältää asetukset ja jokaisen lauseen Whisper-litteroinnin.
- `kansio/index.html` on paikallinen kuuntelusivu, jonka voi avata komennolla `open`.

Valitsin `--until-s 60` lopettaa sen kappaleen jälkeen, jonka aikana minuutti täyttyy. Valitsimella `--paragraphs N` skripti lukee N ensimmäistä kappaletta. Ehdokasvalinta on tässä skriptissä oletuksena päällä.

## Pythonista

Selkein tapa on ajaa skriptit erillisinä prosesseina f5-fi:n omalla Pythonilla. Silloin projektin oma ympäristö ei tarvitse PyTorchia eikä F5:tä:

```python
import subprocess
F5 = "/Users/jkojo22/Koodausprojektit/Kielimallit/f5-fi"
subprocess.run([f"{F5}/.venv/bin/python", "-I", f"{F5}/scripts/speak.py", teksti,
                "--candidates", "3",          # ilman --ref käytössä on suositeltu viite
                "--out", polku], check=True)
```

Jos tuotat monta lausetta ja ajat koodia f5-fi:n omalla ympäristöllä, lataa malli vain kerran. Mallin lataus kestää noin 30 sekuntia.

```python
import sys; sys.path.insert(0, "/Users/jkojo22/Koodausprojektit/Kielimallit/f5-fi/scripts")
import f5fi
tts = f5fi.load_model()                       # perusmalli; hienosäädetty: load_model("<polku checkpointiin>")
ref = f5fi.DEFAULT_REF                        # suositeltu viite
ref_text = open(ref[:-4] + ".txt", encoding="utf-8").read().strip()
res = f5fi.synthesize(tts, ref, ref_text, "Tekstiä puheeksi.", "puhe.wav", candidates=3)
```

Rooliharjoittelu-projekti käyttää mallia polun `models/f5-fi` kautta. Polku on symbolinen linkki f5-fi:n kansioon `base/`.

## Tekstin kirjoittaminen mallille

- **Kirjoita luvut sanoina:** "kello kymmenen", "kaksisataa euroa". Moduuli ei muuta numeroita sanoiksi.
- **Kirjoita lyhenteet auki:** "esimerkiksi", ei "esim.". Kirjainlyhenteet kirjoitetaan niin kuin ne äännetään, esimerkiksi "ee-uu". Tätä ei ole testattu kuuntelukokeessa, joten kuuntele tulos.
- Moduuli muuttaa lauseen alkukirjaimen ja ison Ä:n pieneksi ja hoitaa osan rajageminaatiosta: 1. infinitiivin hallitsevan verbin jälkeen ("voisitko selittää sen" → "selittääs sen") sekä kieltomuodon jälkeen ("ei kannata syöttää" → "kannatas", "ei mennä" → "mennäs"). Älä kirjoita näitä itse. Muut tapaukset ovat seuraavassa luvussa.
- Puhekieltä voi kirjoittaa sellaisenaan: "Mä en ihan tajunnu".
- Yksisanaiset repliikit, kuten "Joo.", toimivat. Whisper kuulee ne kuitenkin usein väärin, joten arvioi ne kuuntelemalla.

## Kirjoitusasukorjaukset, joita moduuli ei vielä tee

Nämä korjaukset hyväksyttiin kuuntelussa Koulutusmateriaalit-projektissa 10.–11.11.2026. Suurin osa niistä siirtyi moduuliin f5-fi:n omien sokkokokeiden jälkeen 12.11.2026, joten niitä **ei enää kirjoiteta itse**: pieni alkukirjain, kahdennus kieltomuodon ja käskymuodon jälkeen sekä luettelossa, kahdennus yhdyssanan sisällä ("saatettekstin"), tavuviiva yhdyssanan vokaalirajalle ("pitopalvelu-yrittäjä") ja kaksoispisteen jako kahdeksi otoksi. Alla ovat ne, joita moduuli ei tee. h vokaalin edellä hylättiin yleissääntönä, koska h kuului usein oikeana h:na. Nämä korjaukset tehdään tekstiin, joka annetaan mallille. Näytettävä teksti (tekstitys, käsikirjoitus) pidetään oikeinkirjoitettuna, joten pidä mallin teksti erillisessä kentässä.

Käytä korjausta vain, kun käyttäjä kuulee virheen. Älä tee niitä kaikkiin lauseisiin etukäteen.

| Virhe kuuntelussa | Kirjoitusasu mallille | Esimerkki |
|---|---|---|
| Sanat liimautuvat yhteen, kun seuraava sana alkaa vokaalilla (kurkkusulkeuma puuttuu) | h laukaisevan sanan loppuun. Kuuntele tulos: h voi kuulua oikeana h:na ("hikkunan"). Heittomerkki, pilkku, viiva ja k hylättiin. | "ei tarvitseh ymmärtää", "pitää ymmärtääh itse" |
| Rajageminaatio puuttuu kohdassa, jota moduuli ei tunnista (adverbi, infinitiivi ilman hallitsevaa verbiä, sana jolla on myös substantiivitulkinta) | Seuraavan sanan alkukonsonantti laukaisevan sanan loppuun | "tavoitteena on päättäät tietoisesti", "kiinnik kaiteesta", "kertoat taustan" |
| Pilkun kohdalla pisteen kaltainen tauko ja lasku ennen sivulausetta | Pilkku pois mallin tekstistä | "palveluun miettimättä käytetäänkö" |

Huomioita:

- **Aiemmin käsin korjatut tekstit toimivat yhä.** Moduuli ei kahdenna uudelleen sanaa, jonka olet jo merkinnyt ("saatettekstin", "kysyk"), eikä lisää toista tavuviivaa. Uusiin teksteihin näitä ei kuitenkaan enää kirjoiteta itse.
- **`--raw` ohittaa myös kaksoispisteen jaon.** Jos haluat jakaa raakatekstin, jaa se itse ja liitä osat 0,3 sekunnin tauolla.
- **Käsin merkitty sana katkaisee moduulin merkinnän.** Moduuli tunnistaa sanat Voikolla, eikä Voikko tunne käsin merkittyjä muotoja, kuten "kirjoittaas". Jos merkitset sanan käsin, moduuli ei enää tunnista sitä seuraavan sanan laukaisijaksi. Kirjoita silloin myös seuraava kahdennus käsin.
- **Jos kieltomuodon kahdennus kuulostaa väärältä,** anna lause valitsimella `--raw` ja kirjoita teksti itse. Sokkokokeessa "ei kannatat tehdä" oli ainoa merkitty lause, joka kuulosti huonommalta.
- **Pilkun tauot:** lauseen sisäisten taukojen lyhentäminen enintään 0,15 sekuntiin paransi useimpia lauseita. Moduuli tekee sen pyydettäessä: `speak.py --max-pause 0.15` tai `f5fi.synthesize(..., max_pause=0.15)`. Päälauseiden välinen pilkku ("aikaa, ja aika on") ja luetteloa edeltävä pilkku ("varmana, esimerkiksi", 0,25 s) tarvitsivat kuitenkin pidemmän tauon. Silloin jätä raja pois tai anna lisäksi `--longest-pause 0.25` (`longest_pause=0.25`), joka asettaa lauseen pisimmän tauon juuri tuon mittaiseksi. Asetus ei ole oletuksena päällä. Kuuntele ennen kuin lyhennät.

## Siemenvalinta lausepainoa ja intonaatiota varten

Malli lukee osan lauseista tasaisesti: uusi termi jää ilman painoa ("nimeä metakognitiivinen laiskuus"), konnektiivin jälkeinen sana ei nouse esiin ("silti vaikeampaan", "siksi kahdella") ja luettelo katkeaa lopun kaltaiseen laskuun. Tauot, pilkut ja lauseen jakaminen eivät auttaneet. Lausepaino vaihtelee kuitenkin siemenen mukaan, joten toimiva keino on tuottaa samasta tekstistä useita ottoja ja antaa käyttäjän valita korvalla. Neljässä lauseessa viidestä kelvollinen otto löytyi kahdeksasta.

```bash
$PY -I $F5/scripts/speak.py "ilmiöstä käytetään nimeä metakognitiivinen laiskuus." --seeds 4-11 --out /polku/kansio
```

Valitsin `--seeds` tuottaa yhden oton jokaisella siemenellä (`lause01-s04.wav` …) ja kokoaa kansioon kuuntelusivun `index.html`, jolla käyttäjä vertaa ottoja ja valitsee parhaan. Valinnat näkyvät sivun alareunassa kopioitavana tekstinä. Kun ajat komennon uudelleen toisella tekstillä ja samalla kansiolla, lause lisätään samalle sivulle. Valmiita ottoja ei tehdä uudelleen. Tiedot ovat tiedostossa `siemenet.json`. Älä käytä tässä `--candidates`-valitsinta, koska se valitsee oton Whisperin pisteillä, jotka eivät erota intonaatiota. Valitsimet eivät käy yhdessä.

Jos lauseita on useita, lataa malli kerran Pythonissa:

```python
tts = f5fi.load_model()
ref = f5fi.DEFAULT_REF
ref_text = open(ref[:-4] + ".txt", encoding="utf-8").read().strip()
for nimi, teksti in lauseet:
    f5fi.seed_takes(tts, ref, ref_text, teksti, "/polku/kansio", f5fi.parse_seeds("4-11"), name=nimi)
```

Luettelossa ja-sana voi tarvita pidemmän välin kuin mikään siemen antaa. Silloin auttoi pilkku ennen ja-sanaa mallin tekstissä yhdessä siemenvalinnan kanssa: "tekoäly voi luonnostella, ideoida, ja haastaa." (siemen 8). Pilkku ei kuulu näytettävään tekstiin.

## Nopeus ja tuloste

- Laite on M3-Macin MPS. Mallin lataus kestää noin 30 sekuntia ja lyhyen lauseen tuottaminen 10–25 sekuntia. Minuutin luenta kolmella ehdokkaalla kestää noin 9–10 minuuttia, joten aja pitkät tekstit taustalla.
- Valitsin `--nfe 16` tekee tuottamisesta noin kaksi kertaa nopeampaa, mutta laadusta ei ole tehty kuuntelukoetta.
- Tuloste on 24 kHz:n mono-WAV. Koneella ei ole FFmpegiä. Jos tarvitset muun tiedostomuodon, käytä macOS:n `afconvert`-työkalua.
- Kaikki toimii ilman verkkoyhteyttä, koska mallit ovat valmiiksi välimuistissa.

## Tunnetut puutteet

- Luenta on tasaista. Eläytymistä parannetaan uusilla viitenäytteillä (nauhoitusohjeen vaihe A2) ja myöhemmin hienosäädöllä.
- Lausepaino ja luettelon intonaatio puuttuvat usein. Ennen hienosäätöä ainoa keino on siemenvalinta (katso yllä).
- Joissakin sanoissa on satunnaisia vaihevirheitä. Toisella siemenellä (`--seed 2`) virhe usein katoaa.
- Lyhyt lause voi katketa lopusta. Esimerkiksi "Kiitos avusta" katkesi osassa kokeista. Kuuntele lyhyet lauseet, ja kokeile tarvittaessa toista siementä.
- Nopealla puhekieliviitteellä sanan alkukonsonantti voi jäädä pois.

## Kun malli päivittyy

Kun hienosäädetty malli valmistuu, se tallennetaan kansioon `$F5/checkpoints/` ja otetaan käyttöön valitsimella `--ckpt` (`load_model(ckpt)` Pythonissa). Samalla tämä ohje päivitetään. Lue ohje uudelleen, ennen kuin aloitat uutta puhetyötä: `$F5/docs/kaytto-muissa-projekteissa.md`.
