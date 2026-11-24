# Ohje Rooliharjoittelulle: F5-fi-puhepalvelun käyttöönotto

Tämä ohje on tarkoitettu Rooliharjoittelu-projektissa työskentelevälle Claudelle ja sen käyttäjälle. Se on itsenäinen: kaikki tarvittava (rajapinta, tiedostot, asiakaskoodi) on tässä. Päivitetty 2026-11-24. Lähde: repositorio `juusokojo/F5-FI-Jooseppi`, haara `claude/great-cori-98yi8a`.

## 0. Tehtävä

Rooliharjoittelun LLM tuottaa hahmon vastaukset tekstinä. Ne muutetaan puheeksi **puhepalvelulla**: F5-fi-malli ajaa Lehmuksessa A30-GPU:lla Slurm-työnä, ja sovellus kutsuu sitä HTTP:llä. Palvelu on jo rakennettu ja testattu valetaustalla; sinun tehtäväsi on liittää Rooliharjoittelu siihen:

1. yhteys palveluun (osoite ja avain tiedostoista, selviytyminen uudelleenkäynnistyksistä)
2. LLM:n tulosteen rakenne: mikä ääni ja mikä tunne (viiteäänite) kullekin repliikille
3. samanaikaisten keskustelujen rajaus (uutta käyttäjää ei päästetä sisään, jos puhekapasiteetti on täynnä)
4. puheen tuotto lause kerrallaan ja toisto
5. virhetilanteet (palvelu alhaalla, varattu, väärä tunne) ilman että harjoittelu keskeytyy
6. testit ilman GPU:ta

## 1. Selvitä käyttäjältä ennen koodausta

| Kysymys | Miksi |
|---|---|
| Missä on f5-fi-repositorio Lehmuksessa? (tässä ohjeessa `<F5>`) | Rekisteri, asiakaskoodi ja käynnistysskriptit ovat siellä |
| Pyörittääkö Rooliharjoittelu samalla Unix-käyttäjällä kuin puhepalvelu? | `~/.f5-palvelu/avain` on 600, joten vain sama käyttäjä lukee sen. Tarkista `id` ja `ls -l ~/.f5-palvelu`. Jos käyttäjä on eri, ratkaisu sovitaan erikseen (älä löysää avaimen oikeuksia ilman käyttäjää) |
| Onko puhepalvelun työ käynnissä? | `squeue -u $USER --name=f5fi-puhe`. Ellei: `cd <F5> && sbatch slurm/serve.sbatch` ja odota, että `~/.f5-palvelu/osoite.json` ilmestyy |
| Mitkä viiteäänitteiden (tunteiden) nimet Rooliharjoittelussa on käytössä, esim. `tunne_artynyt_a`? | Palvelu tuntee vain rekisterin nimet. Vertaa Rooliharjoittelun nimiä komennon `GET /voices` (kohta 3.4) tulokseen. Eroavat nimet ovat virhe, ei oletus (400) |
| Montako keskustelua yhtä aikaa? | Aloita arvolla 2. Oikea luku mitataan (kohta 4, askel 9) |
| Missä kielessä ja kehyksessä Rooliharjoittelu on? | Liitteen A asiakas on Python (vain vakiokirjasto). Muussa kielessä toteuta kohdan 3 sopimus |

## 2. Tiedostot

**Palvelun kirjoittamat ajonaikaiset tiedostot** (kansio `~/.f5-palvelu`, oikeudet 700; ei repositoriossa, ei versionhallintaan):

| Tiedosto | Sisältö |
|---|---|
| `~/.f5-palvelu/osoite.json` | `{"url": "http://<solmu>:<portti>", "job": <työnumero>, "started": "<aika>"}`. Ilmestyy, kun palvelu on valmis; poistuu, kun se sammuu |
| `~/.f5-palvelu/avain` | Palvelun uusi satunnainen avain, pelkkä merkkijono. **Vaihtuu joka käynnistyksellä** |

Muut tiedostot samassa kansiossa (`current.json`, `<työnumero>.json`, `avaimet.json`) ovat palvelun omia. Älä käytä niitä.

**F5-fi-repositoriosta (`<F5>`)** kopioitavat tai luettavat:

| Tiedosto | Käyttö |
|---|---|
| `<F5>/scripts/puhepalvelu_client.py` | Asiakas, kopioi Rooliharjoitteluun (sama koodi on liitteessä A) |
| `<F5>/slurm/voices.json` | Äänirekisteri: äänet ja viitenimet. **Vain luku**; ajantasaisin luettelo saadaan kutsulla `GET /voices` |
| `<F5>/slurm/voices.example.json` | Esimerkkirekisteri (kehitysajoon valetaustalla) |
| `<F5>/slurm/serve.sbatch` | Palvelun käynnistys: `sbatch slurm/serve.sbatch`. Loki: `f5fi-puhe-<työ>.log` siinä hakemistossa, josta `sbatch` ajettiin |
| `<F5>/scripts/serve_bench.py` | Kuormamittari (kohta 4, askel 9) |
| `<F5>/scripts/serve.py` | Palvelu itse; `--backend fake` ajaa sen ilman GPU:ta (askel 8) |
| `<F5>/docs/palvelin-lehmus.md` | Palvelimen asennus, elinkaari ja mitoitus |
| `<F5>/docs/kaytto-muissa-projekteissa.md` | Yleinen käyttöohje muille projekteille |
| `<F5>/AANI-JA-MALLI.md` | Äänten lisenssi ja käyttöehdot (kohta 5 tiivistää) |

**Rooliharjoittelun puolelle** (ehdotus, sovita olemassa olevaan rakenteeseen): `puhe/puhepalvelu_client.py` (asiakas), `puhe/paikat.py` (kohta 4, askel 5), `puhe/putki.py` (askel 6) ja `tests/test_puhe.py` (askel 8).

## 3. Rajapinta

### 3.1 Löytäminen

Lue `osoite.json` ja `avain`. **Jos yhteys katkeaa tai avain hylätään (401), lue molemmat tiedostot uudelleen ja yritä kerran.** Työ vaihtuu viikon välein tai kaatuessa, ja silloin portti ja avain vaihtuvat. Jos `osoite.json` puuttuu, palvelu ei ole käynnissä: käytä tekstitilaa. Tiedosto voi jäädä jäänteeksi, jos työ tapetaan väkivalloin, joten `GET /health` kertoo, onko osoitteessa oikeasti palvelu. Palvelu on klusterin sisäverkossa ja käyttää HTTP:tä ilman salausta; **ohita ympäristön proxy-asetukset** tälle yhteydelle (Liitteen A asiakas tekee sen).

### 3.2 `GET /health` (ei avainta)

```json
{"ok": true, "voices": ["jooseppi", "justiina", "justiina2", "valdemar"], "queue": 0}
```

`ok` on `false` (HTTP 503), kun palvelu lataa malleja tai sammuu. `queue` on jonossa odottavien lauseiden määrä.

### 3.3 `POST /synthesize`

Otsake `Authorization: Bearer <avain>`, runko:

```json
{"voice": "justiina2", "clip": "tunne_artynyt_a", "text": "Teksti, enintään neljä lausetta.", "seed": 1}
```

Vastaus 200: `audio/wav`, **mono, 16 bit, 24 kHz**. Otsakkeet: `X-Voice`, `X-Emotion` (käytetty viite), `X-Seed`, `X-Sentences`, `X-Duration-S`, `X-Wait-S` (jonotus) ja `X-Gen-S` (generointi).

- `voice`: `jooseppi`, `justiina`, `justiina2` tai `valdemar` (isot ja pienet kirjaimet eivät merkitse).
- `clip`: viiteäänitteen nimi. Se valitsee äänitteen **ja** tunteen. Tuntematon nimi on 400 (ei oletusta).
- `seed`: valinnainen kokonaisluku. Ilman sitä käytetään viitteen oletussiementä. Siemen vaikuttaa lausepainoon ja intonaatioon. **Pidä siemen samana saman hahmon repliikeissä**, ellei vaihtelua haluta.
- `text`: tavallista kirjoitettua suomea, enintään 600 merkkiä ja oletuksena enintään **4 lausetta** (pidempi on 400). Palvelu jakaa tekstin lauseiksi, generoi ne erikseen ja liittää 0,3 s tauolla.

**Tekstin valmistelu.** Palvelu tekee suomen ääntämiskorjaukset itse (Voikko: "tervetuloa" → "tervettuloa", pieni alkukirjain, kaksoispisteen jako): **älä tee niitä omassa koodissasi**. Se poistaa myös `*huokaisee*`, `[naurahtaa]`, hymiöt ja markdownin. Se **ei** muuta lukuja tai lyhenteitä sanoiksi, joten pyydä LLM:ää kirjoittamaan ne sanoina ("kello kymmenen", ei "10:30"; "esimerkiksi", ei "esim."). Pidä näytettävä ja puhuttava teksti erillään.

### 3.4 `GET /voices` (avain vaaditaan)

Palauttaa äänet ja niiden viitenimet. Käytä tätä LLM:n kehotteen ja validoinnin pohjana:

```json
{"justiina2": {"default_emotion": "neutraali", "emotions": ["neutraali", "tunne_artynyt_a", "..."]}, "...": {}}
```

### 3.5 Virheet

Virheet ovat JSON-muodossa `{"error": "..."}`. Virheilmoitus kertoo, mitä on olemassa.

| Koodi | Merkitys | Mitä sovellus tekee |
|---|---|---|
| 401 | väärä avain | asiakas lukee avaimen uudelleen ja yrittää kerran; jos edelleen 401, virhe (`Epaonnistui`) |
| 400 | tuntematon ääni tai viite, tyhjä tai liian pitkä teksti, virheellinen JSON | sovelluksen virhe: kirjaa lokiin, käytä äänen oletusviitettä, älä yritä samaa uudelleen |
| 503 + `Retry-After` | jono täynnä, lause odotti yli 10 s tai palvelu käynnistyy | tilapäinen: odota `Retry-After` tai jatka ilman puhetta. Myöhästynyttä puhetta ei kannata soittaa |
| 500 | synteesi epäonnistui | tämä repliikki ilman puhetta; seuraavaa voi yrittää |
| ei yhteyttä | palvelu alhaalla, siirtymässä tai työ päättynyt | asiakas lukee tiedostot uudelleen ja yrittää kerran; sitten tekstitila ja uusi yritys 15 s välein |

```bash
D=~/.f5-palvelu; URL=$(python3 -c "import json;print(json.load(open('$D/osoite.json'))['url'])"); KEY=$(cat $D/avain)
curl -s --noproxy '*' $URL/health
curl -s --noproxy '*' -H "Authorization: Bearer $KEY" $URL/voices
curl -s --noproxy '*' -H "Authorization: Bearer $KEY" -d '{"voice":"justiina2","clip":"neutraali","text":"Tämä on koe."}' $URL/synthesize -o koe.wav
```

## 4. Toteutus askel askeleelta

Jokaisella askeleella on hyväksymisehto: etene vasta, kun se täyttyy.

**Askel 1: yhteyskoe.** Aja Lehmuksessa komennot kohdasta 3.5 tai `python <F5>/scripts/puhepalvelu_client.py --health`. *Hyväksymisehto:* `ok: true`, neljä ääntä listassa, ja `--voice justiina2 --clip neutraali -o koe.wav "Tämä on koe."` tuottaa kuuluvan WAV-tiedoston. Jos ei onnistu: tarkista työ (`squeue`), tiedostojen oikeudet ja käyttäjä (kohta 1), ja lue palvelun loki (`f5fi-puhe-<työ>.log`).

**Askel 2: asiakas projektiin.** Kopioi liitteen A koodi (tai `<F5>/scripts/puhepalvelu_client.py`) Rooliharjoitteluun. Älä kirjoita omaa HTTP-koodia. Yksi `Puhepalvelu()`-olio koko sovellukselle riittää: se päivittää osoitteen ja avaimen itse. Jos tiedostot ovat muualla kuin `~/.f5-palvelu`, aseta `F5_PALVELU_DIR`. *Hyväksymisehto:* sovelluksen oma testi kutsuu `health()`-metodia ja saa vastauksen.

**Askel 3: LLM:n tuloste ja ohjeistus.** Hae `voices()` sovelluksen käynnistyessä ja yhteyden palautuessa (älä kovakoodaa nimiä). LLM palauttaa jokaisesta repliikistä rakenteen, ja sovellus validoi sen:

```python
import json

def tulkitse(llm_vastaus, ääni, äänet):
    """llm_vastaus: JSON-merkkijono {"teksti": "...", "tunne": "<viitteen nimi>"}. Palauttaa (teksti, viite)."""
    oletus = äänet[ääni]["default_emotion"]
    try:
        d = json.loads(llm_vastaus)
        teksti, tunne = str(d["teksti"]).strip(), str(d.get("tunne", "")).strip().lower()
    except (ValueError, KeyError, TypeError):
        return llm_vastaus.strip(), oletus          # pelkkä teksti: oletustunne
    return teksti, tunne if tunne in äänet[ääni]["emotions"] else oletus   # tuntematon tunne: ei virhettä käyttäjälle
```

Kehotteeseen (täytä sulkeissa olevat palvelun vastauksesta): *"Vastaa JSON-muodossa `{"teksti": "...", "tunne": "..."}`. Teksti on enintään kolme lausetta tavallista kirjoitettua suomea; kirjoita luvut ja lyhenteet sanoina; älä käytä näyttämömerkintöjä, hymiöitä tai markdownia. Tunne on tasan yksi näistä: {palvelun luettelo hahmon äänelle}."* *Hyväksymisehto:* testi, jossa tuntematon tunne, puuttuva `tunne`-kenttä ja pelkkä teksti tuottavat kaikki kelvollisen (teksti, viite) -parin.

**Askel 4: hahmot ja äänet.** Anna jokaiselle hahmolle asetuksiin `ääni`, oletusviite ja siemen (kiinteä, esim. 1):

| Ääni | Kuvaus | Malli (palvelu valitsee) |
|---|---|---|
| `jooseppi` | aikuisen miehen ääni | Joosepin hienosäätö |
| `justiina` | tunteikas aikuisen naisen ääni | sama malli, oma viite |
| `justiina2` | rauhallinen aikuisen naisen ääni | sama malli, oma viite |
| `valdemar` | lapsen ääni | oma hienosäätö |

Älä yhdistele malleja ja viitteitä itse: palvelu hoitaa sen äänen mukaan. *Hyväksymisehto:* jokainen hahmo, jolla on ääni, tuottaa puhetta omalla äänellään (kuuntele jokainen kerran).

**Askel 5: paikat (sisäänpääsy).** Rajaa samanaikaiset keskustelut sovelluksessa: uusi keskustelu pääsee alkamaan vain, jos paikka on vapaana ja palvelu on valmis. Palvelu itse ei pidä istuntoja, vaan se rajaa vain jonoa (503).

```python
import threading

class Paikat:
    """Rajoittaa samanaikaisia keskusteluja. n tulee mittauksesta (askel 9); aloita arvolla 2."""
    def __init__(self, n):
        self.n, self._sem = n, threading.BoundedSemaphore(n)
    def ota(self):                       # True = keskustelu saa alkaa
        return self._sem.acquire(blocking=False)
    def vapauta(self):                   # kutsu keskustelun päättyessä, myös virhetilanteessa (try/finally)
        self._sem.release()

def voiko_aloittaa(puhe, paikat):
    """Palauttaa (kyllä/ei, syy). Syy näytetään käyttäjälle."""
    try:
        h = puhe.health()
    except Exception:
        return False, "puhepalvelu ei ole käytössä"
    if not h["ok"]:
        return False, "puhepalvelu käynnistyy"
    if h["queue"] >= 2:
        return False, "puhepalvelu on kuormitettu"
    return (True, "") if paikat.ota() else (False, "kaikki paikat ovat käytössä")
```

Kun `voiko_aloittaa` palauttaa ei, tarjoa käyttäjälle jonotusta tai tekstitilaa. *Hyväksymisehto:* testi, jossa `n + 1`:s keskustelu ei pääse alkamaan ja paikka vapautuu keskustelun päättyessä.

**Askel 6: lauseputki ja toisto.** Puheen ensimmäinen lause kuuluu heti, kun se on valmis, joten älä odota koko vastausta. Jaa repliikki lauseiksi samalla säännöllä kuin palvelu (`(?<=[.!?])\s+(?=[A-ZÅÄÖ])`), lähetä lauseet **yksi kerrallaan** (enintään 2 kutsua yhtä aikaa keskustelua kohden, jottei jono täyty) ja soita ne järjestyksessä. Jos LLM:n vastaus suoratoistuu, aloita ensimmäisen lauseen puhe heti, kun sen loppu on tullut.

```python
import re
LAUSEET = re.compile(r"(?<=[.!?])\s+(?=[A-ZÅÄÖ])")

def puhu_repliikki(puhe, ääni, viite, siemen, teksti, soita):
    for lause in LAUSEET.split(teksti.strip()):
        if lause.strip():
            p = puhe.synthesize(ääni, viite, lause, siemen, wait_s=4)   # odottaa varattua palvelua enintään 4 s
            soita(p.wav)                                                # WAV: mono, 16 bit, 24 kHz
```

Pidä käyttöliittymän teksti ja puheen teksti synkassa. Jos ääni valmistuu yli 10 s liian myöhään (käyttäjä on jo edennyt), älä soita sitä. Toistuvat vakiorepliikit (tervehdykset) voi tuottaa etukäteen ja tallentaa välimuistiin avaimella (ääni, viite, siemen, teksti). *Hyväksymisehto:* kolmen lauseen repliikistä ensimmäinen kuuluu ennen kuin toinen on valmis.

**Askel 7: virhetilanteet.** Harjoittelu ei saa pysähtyä puheen virheeseen: jokainen poikkeus tuottaa tekstin ilman ääntä.

| Poikkeus (Liite A) | Toimi |
|---|---|
| `EiKaytossa` | Merkitse puhe pois päältä, näytä tekstitila, tarkista `health()` 15 s välein ja palauta puhe, kun `ok` |
| `Varattu` | Jätä tämä repliikki ilman ääntä (tai odota `retry_after`, jos ehdit); älä tee uusia kutsuja tulvana |
| `VirheellinenPyynto` | Sovelluksen virhe: kirjaa, yritä kerran äänen oletusviitteellä, ilmoita kehittäjälle |
| `Epaonnistui` | Kirjaa, tämä repliikki ilman ääntä |

Älä kirjaa avainta lokiin äläkä näytä sitä käyttäjälle. *Hyväksymisehto:* testi, jossa asiakas korvataan versiolla, joka heittää kunkin poikkeuksen, ja keskustelu jatkuu tekstinä.

**Askel 8: testit ilman GPU:ta.** F5-fi-repon palvelu käynnistyy valetaustalla, joka tuottaa sävelen mallin sijaan, ja se noudattaa täsmälleen samaa sopimusta (tarvitsee vain `fastapi`, `uvicorn`, `numpy`, `soundfile` ja `pydantic`; ei torchia):

```bash
python <F5>/scripts/serve.py --voices <F5>/slurm/voices.example.json --backend fake --contract-dir /tmp/f5-testi &
F5_PALVELU_DIR=/tmp/f5-testi python <F5>/scripts/puhepalvelu_client.py --voices
```

Käytä tätä sovelluksen integraatiotesteissä (`F5_PALVELU_DIR=/tmp/f5-testi`). Valepalvelun äänet ja viitteet tulevat esimerkkirekisteristä: `jooseppi` ja `justiina` (`neutraali`, `iloinen`, `huolestunut`, `vihainen`), `justiina2` (`neutraali`) ja `valdemar` (`neutraali`, `iloinen`). Testaa lisäksi: palvelun uudelleenkäynnistys (uusi portti ja avain) kesken keskustelun ja palvelun puuttuminen.

**Askel 9: mittaus ja käyttöönotto.** Kun oikea palvelu on käynnissä, mittaa kapasiteetti (ks. `<F5>/docs/palvelin-lehmus.md`, luku 5):

```bash
python <F5>/scripts/serve_bench.py --voice justiina2 --clip neutraali --users 3 --turns 6 --think-s 8
```

Kasvata `--users`-lukua, kunnes äänen valmistumisajan p95 ylittää sen, minkä hyväksyt (puhutulle vastaukselle 1,5–2 s on kohtuullinen raja). Viimeinen hyvä luku on `Paikat(n)`:n `n`. Kuuntele samalla jokainen ääni ja viite kerran palvelimella: Macilla valitut siemenet eivät ole siirrettävissä (kohta 6). *Hyväksymisehto:* `n` on kirjattu sovelluksen asetuksiin, ja jokaiselle hahmolle on kuultu hyväksyttävä ääni.

## 5. Käyttöehdot (pakolliset)

Äänten ja mallien ehdot ovat tiedostossa `<F5>/AANI-JA-MALLI.md`. Rooliharjoittelussa ne tarkoittavat:

- Käyttö vain **Oulun yliopiston opetukseen ja tutkimukseen**. Ei kaupallista käyttöä (perusmallin lisenssi CC BY-NC 4.0).
- **Merkintä:** kun puhetta esitetään käyttäjille, kerro, että se on tekoälyn tuottamaa, ja nimeä ääni, esimerkiksi: *"Puhe on tuotettu tekoälyllä. Ääni: Justiina2, F5-TTS Finnish -malliin perustuva, CC BY-NC 4.0."* (vastaavasti `Jooseppi (Juuso Kojo)`, `Justiina`, `Valdemar`).
- Kielletty: esiintyminen äänen puhujana tai sanojen laittaminen hänen suuhunsa, Justiinan, Justiina2:n ja Valdemarin puhujien henkilöllisyyden selvittäminen, harhaanjohtaminen ja huijaaminen, uusien äänimallien kouluttaminen näillä äänillä.
- Älä julkaise tuotettua puhetta verkkoon ilman käyttäjän lupaa. Älä kopioi painoja tai viiteäänitteitä Rooliharjoitteluun, älä tee puhepalvelusta yleisesti kutsuttavaa, äläkä kutsu sitä suoraan selaimesta: kutsut tehdään sovelluksen palvelinpuolelta, eikä avain ole koskaan selainkoodissa.
- Valdemar on lapsen ääni: käytä sitä vain käyttäjän hyväksymissä harjoittelutilanteissa.

## 6. Tunnetut rajoitteet

- **Ei suoratoistoa.** Ääni tulee vasta, kun lause on kokonaan generoitu, siksi lause kerrallaan (askel 6).
- **Nopeus on tuntematon, kunnes se mitataan.** Palvelua ei ole vielä ajettu oikealla mallilla GPU:lla (valetausta testattu).
- **Palvelun työ vaihtuu viikon välein** (7 vrk aikaraja). Välillä voi olla katko; sovelluksen pitää kestää se (kohdat 3.1 ja askel 7).
- **Siemenet:** Macilla kuunnellut ja valitut siemenet tuottavat GPU:lla eri oton, joten kuuntele ne uudelleen.
- **Puhekieli:** Voikko ei tunne puhekielisiä muotoja, joten niiden rajageminaatiota ei merkitä ("mä en tajunnu" luetaan sellaisenaan).
- **Yksi lause voi epäonnistua satunnaisesti** (ylimääräinen tavu, katkennut loppu). Toinen siemen korjaa usein; tämän vuoksi sama siemen kaikilla repliikeillä ei takaa täydellistä laatua. Ehdokasvalinta ei ole palvelussa mukana (se kolminkertaistaisi ajan).
- **Jono on lyhyt** (oletus 4 lausetta, yksi työläinen): kuormassa osa kutsuista saa 503:n. Se on suunniteltu käytös, ei vika.

## Liite A: `puhepalvelu_client.py`

Sama koodi on tiedostossa `<F5>/scripts/puhepalvelu_client.py`. Vain Pythonin vakiokirjasto. Se lukee osoitteen ja avaimen, ohittaa ympäristön proxyt, lukee tiedostot uudelleen yhteysvirheessä tai 401:ssä ja palauttaa kullakin virhetyypillä oman poikkeuksensa.

```python
"""Client for the F5-fi puhepalvelu (Lehmus). Python standard library only, so the file can be copied as it is.

    from puhepalvelu_client import Puhepalvelu, EiKaytossa, Varattu, VirheellinenPyynto

    puhe = Puhepalvelu()                      # reads ~/.f5-palvelu/osoite.json and ~/.f5-palvelu/avain
    p = puhe.synthesize("justiina2", "tunne_artynyt_a", "Tämä on koe. Kuuluuko ääni?", wait_s=3)
    open("koe.wav", "wb").write(p.wav)        # mono, 16 bit, 24 kHz

Command line (a quick check that the connection works):

    python puhepalvelu_client.py --health
    python puhepalvelu_client.py --voices
    python puhepalvelu_client.py --voice justiina2 --clip neutraali -o koe.wav "Tämä on koe."

The service writes a new key and may move to a new node and port whenever its Slurm job is replaced. This client therefore
reads the two files again and tries once more when the connection fails or the key is refused, which is all an application
needs to survive a restart. Proxy settings from the environment are ignored on purpose: the service is on the cluster's
internal network.
"""
import argparse
import dataclasses
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

DEFAULT_DIR = os.path.expanduser(os.environ.get("F5_PALVELU_DIR", "~/.f5-palvelu"))  # F5_PALVELU_DIR: if elsewhere


class PuhepalveluError(Exception):
    pass


class EiKaytossa(PuhepalveluError):
    """The service is not running, not ready, or cannot be reached: use text only or tell the user."""


class Varattu(PuhepalveluError):
    """503: the queue is full, the line waited too long, or the service is starting. Try again after retry_after seconds."""

    def __init__(self, message, retry_after=5.0):
        super().__init__(message)
        self.retry_after = retry_after


class VirheellinenPyynto(PuhepalveluError):
    """400: unknown voice or clip, empty or too long text, bad JSON. The message says what is wrong and what exists."""


class Epaonnistui(PuhepalveluError):
    """401 after the files were read again, or 500: the synthesis itself failed."""


@dataclasses.dataclass
class Puhe:
    wav: bytes
    voice: str
    clip: str
    seed: int
    sentences: int
    duration_s: float
    wait_s: float  # time in the queue
    gen_s: float  # time spent generating


class Puhepalvelu:
    def __init__(self, directory=DEFAULT_DIR, timeout=60.0):
        self.dir, self.timeout = directory, timeout
        self.url = self.key = None
        self._lock = threading.Lock()
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    # -- address and key

    def _load(self):
        try:
            with open(os.path.join(self.dir, "osoite.json"), encoding="utf-8") as f:
                url = json.load(f)["url"].rstrip("/")
            with open(os.path.join(self.dir, "avain"), encoding="utf-8") as f:
                key = f.read().strip()
        except (OSError, ValueError, KeyError) as e:
            raise EiKaytossa(f"puhepalvelun osoitetta ei löydy ({self.dir}): {e}") from None
        with self._lock:
            self.url, self.key = url, key

    def _once(self, method, path, body=None, auth=True):
        if self.url is None:
            self._load()
        headers = {"Content-Type": "application/json"} if body is not None else {}
        if auth:
            headers["Authorization"] = f"Bearer {self.key}"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, headers=headers, method=method)
        try:
            with self._opener.open(req, timeout=self.timeout) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()
        except (urllib.error.URLError, ConnectionError, socket.timeout, TimeoutError) as e:
            raise EiKaytossa(f"yhteys puhepalveluun ei onnistu ({self.url}): {e}") from None

    def _request(self, method, path, body=None, auth=True):
        """One request; if the connection fails or the key is refused, read the files again and try once more."""
        try:
            status, headers, data = self._once(method, path, body, auth)
            if status != 401:
                return status, headers, data
        except EiKaytossa:
            pass
        self._load()
        return self._once(method, path, body, auth)

    @staticmethod
    def _error(data):
        try:
            return json.loads(data)["error"]
        except (ValueError, KeyError, TypeError):
            return data[:200].decode("utf-8", "replace")

    # -- interface

    def health(self):
        """{"ok": bool, "voices": [...], "queue": n}. Raises EiKaytossa if nothing answers. ok is False while starting."""
        status, _, data = self._request("GET", "/health", auth=False)
        try:
            return json.loads(data)
        except ValueError:
            raise EiKaytossa(f"/health antoi vastauksen {status}, joka ei ole JSON") from None

    def voices(self):
        """{"justiina2": {"default_emotion": "neutraali", "emotions": ["neutraali", "tunne_artynyt_a", ...]}, ...}"""
        status, _, data = self._request("GET", "/voices")
        if status != 200:
            raise Epaonnistui(f"/voices: {status} {self._error(data)}")
        return json.loads(data)

    def synthesize(self, voice, clip, text, seed=None, wait_s=0.0):
        """Speak `text` (a few sentences) in `voice` with the reference clip `clip`. wait_s: how long in total this call
        may wait for a busy service (503) before it raises Varattu."""
        body = {"voice": voice, "clip": clip, "text": text}
        if seed is not None:
            body["seed"] = seed
        deadline = time.monotonic() + wait_s
        while True:
            status, headers, data = self._request("POST", "/synthesize", body)
            h = {k.lower(): v for k, v in headers.items()}
            if status == 200:
                return Puhe(data, h["x-voice"], h["x-emotion"], int(h["x-seed"]), int(h["x-sentences"]),
                            float(h["x-duration-s"]), float(h["x-wait-s"]), float(h["x-gen-s"]))
            if status == 503:
                retry = float(h.get("retry-after", 5))
                if time.monotonic() + retry <= deadline:
                    time.sleep(retry)
                    continue
                raise Varattu(self._error(data), retry)
            if status == 400:
                raise VirheellinenPyynto(self._error(data))
            raise Epaonnistui(f"{status}: {self._error(data)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="F5-fi puhepalvelun yhteyskoe")
    ap.add_argument("text", nargs="?")
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--health", action="store_true")
    ap.add_argument("--voices", action="store_true")
    ap.add_argument("--voice")
    ap.add_argument("--clip")
    ap.add_argument("--seed", type=int)
    ap.add_argument("-o", "--out", default="koe.wav")
    ap.add_argument("--wait", type=float, default=10.0, help="kauanko saa odottaa varattua palvelua (s)")
    a = ap.parse_args(argv)
    puhe = Puhepalvelu(a.dir)
    try:
        if a.health:
            print(json.dumps(puhe.health(), ensure_ascii=False))
        elif a.voices:
            print(json.dumps(puhe.voices(), ensure_ascii=False, indent=1))
        elif a.voice and a.clip and a.text:
            p = puhe.synthesize(a.voice, a.clip, a.text, a.seed, a.wait)
            with open(a.out, "wb") as f:
                f.write(p.wav)
            print(f"{a.out}: {p.duration_s:.2f} s, siemen {p.seed}, jonossa {p.wait_s:.2f} s, generointi {p.gen_s:.2f} s")
        else:
            ap.error("anna --health, --voices tai --voice, --clip ja teksti")
    except PuhepalveluError as e:
        sys.exit(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
```
