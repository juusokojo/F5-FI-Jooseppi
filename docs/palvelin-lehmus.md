# Puhepalvelu Lehmuksessa (Slurm)

Tämä ohje kuvaa, miten F5-fi-mallia ajetaan palveluna yliopiston GPU-klusterissa niin, että Rooliharjoittelu-sovellus saa lyhyitä puhepurskeita reaaliajassa ja omat erä-ajot (teksti → ääni) käyttävät samaa GPU:ta syrjäyttämättä niitä.

```
Rooliharjoittelu ──(luetaan)──> f5fi-tila/current.json  ←──(kirjoittaa)── serve.py (Slurm-työ, A30)
        │                                                                   │ portinvartija: jono, istunnot
        └────────── HTTP (solmu:portti, avain) ────────────────────────────┤
                                                                            ├─ työläinen 0: mallit (Jooseppi + Valdemar)
Omat erä-ajot ──(erä-avain, matala prioriteetti)────────────────────────────┴─ työläinen 1: mallit …
```

## Mitä on testattu ja mitä ei

| Osa | Tila |
|---|---|
| Jono, prioriteetit, istuntopaikat, aikakatkaisut, työläisen kaatuminen ja uudelleenkäynnistys, avaimet | Testattu (`tests/test_serve.py`, valetaustalla) |
| Signaalit (SIGTERM, SIGUSR1), osoitetiedoston kirjoitus ja siivous, seuraajalle luovutus, sammuminen joutilaana | Testattu oikeana prosessina ja oikeilla signaaleilla |
| `slurm/install.sh` (Python-ympäristö, Voikko lähdekoodista kotihakemistoon, avaimet) | Ajettu läpi Ubuntu-koneella: 118 testiä läpi. `conda`-haara ja klusterin oma käyttöjärjestelmä jäivät testaamatta |
| **Todellinen synteesi GPU:lla** (`F5Backend`) | **Ei testattu.** Painoja ja äänitteitä ei ollut käytettävissä, eikä GPU:ta. Ensimmäinen ajo klusterissa on sen koe |
| `serve.sbatch`, `probe.sbatch` | Syntaksi tarkistettu, ei ajettu Slurmilla |
| Nopeus ja istuntojen enimmäismäärä | **Tuntematon.** Mitataan `serve_bench.py`:llä klusterissa |
| Rooliharjoittelun yhteys palvelimeen | Riippuu verkosta, katso koetyö alla |

## 1. Koe ennen asennusta

```bash
sbatch slurm/probe.sbatch        # lue sitten f5fi-koe-<työ>.log
```

Lokista katsotaan neljä asiaa:

1. **Ajuri ja CUDA.** PyPI:n `torch` (lukitus 2.15.0) on **CUDA 13.2 -käännös** ja tarvitsee riittävän uuden ajurin (suuruusluokkaa 580 tai uudempi, tarkista NVIDIAn CUDA-yhteensopivuustaulukosta). Jos ajuri on vanhempi, `torch.cuda.is_available()` on epätosi. Silloin asenna CUDA 12 -pyörä: `PIP_EXTRA="--extra-index-url https://download.pytorch.org/whl/cu126" bash slurm/install.sh` (edellyttää, että klusteri tavoittaa `download.pytorch.org`-palvelimen ja että sieltä löytyy lukituksen torch-versio; tarkista, mitä indeksi tarjoaa). Vaihtoehto on pyytää ylläpitoa päivittämään ajuri.
2. **Lähtevä verkko.** `pypi.org` tarvitaan pakettien asennukseen, `archive.ubuntu.com` Voikon lähdekoodiin ja sanakirjaan. Jos jokin on kiinni, hae tiedostot toisaalta ja anna ne asennukselle (`VOIKKO_SRC_TARBALL`, `VOIKKO_FI_DEB`). Mallit ladataan etukäteen, joten palvelin ei tarvitse `huggingface.co`-yhteyttä ajossa.
3. **Portin tavoitettavuus.** Loki antaa komennon (`curl http://solmu:portti/`), jonka ajat siltä koneelta, jolla Rooliharjoittelu pyörii. Jos se ei vastaa, solmun portteja ei avata klusterin ulkopuolelle, ja tarvitaan ssh-tunneli kirjautumissolmun kautta tai ylläpidon vastaanottama proxy. Tämä ratkaisee koko arkkitehtuurin, joten tarkista se ensimmäisenä.
4. **Levy.** Ympäristö vie noin 6 Gt (CUDA-kirjastot) ja painot noin 1,4 Gt per malli. Tarkista kotikansion kiintiö ja valitse tarvittaessa `F5_ENV` työkansioon.

## 2. Asennus

```bash
module load conda                 # tai PYTHON=/polku/python3.13
bash slurm/install.sh
```

Skripti tekee kolme asiaa ilman root-oikeuksia:

- luo Python 3.13 -ympäristön (`.env-lehmus`) ja asentaa lukitustiedoston paketit ilman `mlx*`-paketteja;
- **rakentaa Voikon kotihakemistoon** (`~/voikko`): kirjasto `libvoikko` lähdekoodista (tarvitsee `g++` ja `make`) ja sanakirja Ubuntun `voikko-fi`-paketista, joka puretaan Pythonilla ilman `dpkg`:ta. Skripti tarkistaa lopuksi, että "Tervetuloa" muuttuu muotoon "Tervettuloa". Ilman Voikkoa palvelu **kieltäytyy käynnistymästä**, koska kahdennussäännöt jäisivät hiljaa pois;
- luo tilakansion (`~/f5fi-tila`) ja kaksi avainta tiedostoon `avaimet.json` (`interactive` Rooliharjoittelulle, `batch` omille erä-ajoille).

Sen jälkeen kopioi **painot ja äänitteet** (eivät ole repossa): `base/`-kansion sanasto, molemmat hienosäädetyt checkpointit (Jooseppi, Valdemar), viiteäänitteet ja niiden `.txt`-litteraatit sekä Vocos-vokooderi (`~/.cache/huggingface`). Tee `slurm/voices.json` mallista `slurm/voices.example.json`: ääni → checkpoint, tunne → viite + oletussiemen. Sen jälkeen palvelu käynnistetään:

```bash
sbatch slurm/serve.sbatch
squeue -u $USER                          # odota, että työ on RUNNING
cat ~/f5fi-tila/current.json             # ilmestyy, kun mallit on ladattu ja palvelu on valmis
```

Tarkista ennen ensimmäistä ajoa `sinfo -o "%P %G %l"`: osion nimi (`--partition`) ja GPU:n nimi (`--gres=gpu:a30:1`) ovat `serve.sbatch`:ssa arvauksia.

## 3. Elinkaari

| Tapahtuma | Mitä palvelu tekee |
|---|---|
| Käynnistys | Lataa mallit ja lämmittää ne (yksi lause per ääni, jolloin viallinen viite tai checkpoint kaataa käynnistyksen eikä ensimmäistä pyyntöä). **Kirjoittaa osoitteen vasta, kun kaikki on valmista.** |
| Joka 10 s | Päivittää osoitetiedoston (`updated_at`) |
| `scancel` tai aikaraja (SIGTERM) | Ei uusia istuntoja, kesken olevat lauseet valmistuvat (enintään 15 s, koska Slurm tappaa 30 s kuluttua), osoitetiedostot poistetaan, poistuu koodilla 0 |
| SIGUSR1 (15 min ennen aikarajaa, `--signal=B:USR1@900`) | Kirjaa varoituksen. Jos seuraaja on jo valmis, siirtyy tyhjennystilaan |
| Seuraaja valmistuu (uusi työ kirjoittaa `current.json`:n) | Vanha instanssi lopettaa uusien istuntojen otto, antaa käynnissä olevien päättyä ja sammuu itse, kun ne ovat tyhjentyneet |
| Joutilaana (`F5SERVE_IDLE_EXIT_S`) | Valinnainen: sammuu, kun ei käyttöä, ja vapauttaa GPU:n |
| Työläinen kaatuu tai jää jumiin yli 60 s | Prosessi tapetaan ja käynnistetään uudelleen (enintään 3 kertaa), pyyntö saa 503 |

**Viikon rajan ylitys.** `interactive`-osion aikaraja on 7 vuorokautta. Asetuksella `F5SERVE_RESUBMIT=1` jokainen työ tilaa seuraajansa alkamaan 45 min ennen omaa päättymistään, ja seuraaja ottaa osoitteen heti valmistuttuaan. Oletus on pois, koska ketju varaa GPU:n jatkuvasti. Ketju katkaistaan komennoilla `touch ~/f5fi-tila/STOP` ja `scancel --name=f5fi-puhe`. Jos seuraaja joutuu jonoon, syntyy katko, jonka ajan sovelluksen pitää kestää.

**Kysy ylläpidolta:** sopiiko viikon mittainen GPU-varaus palveluksi `interactive`-osiossa vai pitäisikö käyttää `normal`-osiota (14 vrk) tai erillistä palveluosiota. A30 on 24 Gt. Painot ovat noin 1,4 Gt per malli, ja työläistä kohden latautuu kaksi mallia, joten muistia kuluu todennäköisesti vain osa; todellinen käyttö pitää mitata (`nvidia-smi` ajon aikana). Jos klusterissa on MIG-osioita (A30 jakautuu enintään neljään 6 Gt:n osaan), pienempi osa voisi riittää.

## 4. Osoitetiedosto

`~/f5fi-tila/current.json`:

```json
{"version": 1, "job_id": "123456", "status": "ready", "host": "lehmus-g01", "port": 40341,
 "url": "http://lehmus-g01:40341", "updated_at": 1795517912.7, "max_sessions": 4, "voices": ["jooseppi", ...]}
```

Lukusäännöt (toteutettu `f5client.read_address`):ssa:

- tiedostoa ei ole → palvelu ei ole käynnissä;
- `status` ei ole `ready` → ei uusia istuntoja (`draining`);
- `updated_at` yli 45 s vanha → työ on kuollut väkivalloin (esim. solmu kaatui), tiedosto on jäänne.

Tiedoston kirjoitus on atomista, joten puolikasta tiedostoa ei näe. Tiedostossa ei ole avaimia. Tilakansion oikeudet ovat 700, joten sen lukee vain sama käyttäjä; jos sovellus pyörii eri tunnuksella, anna ryhmälle lukuoikeus tarkoituksella.

## 5. Rajapinta

Kaikki paitsi `/healthz` vaativat otsakkeen `Authorization: Bearer <avain>`.

| Kutsu | Mitä |
|---|---|
| `GET /voices` | Äänet ja niiden tunteet. Rakenna LLM:n ohje tästä, niin LLM ei keksi nimiä |
| `POST /sessions` | Ottaa paikan: `201 {session_id, ttl_s, heartbeat_every_s}`. Täynnä: `429` + `Retry-After`. Myös `429 overloaded`, jos viimeisen minuutin jonotus on yli 2 s |
| `POST /sessions/{id}/heartbeat`, `DELETE /sessions/{id}` | Pitää paikan / vapauttaa sen. Ilman sydämenlyöntiä paikka vapautuu 120 s:ssa |
| `POST /speak` | `{voice, text, emotion?, session_id, seed?, nfe?}` → `audio/wav` (24 kHz, 16 bit). Otsakkeet: `X-Emotion` (käytetty), `X-Wait-S`, `X-Gen-S`, `X-Duration-S` |
| `GET /status`, `GET /healthz` | Jonot, työläiset, p50/p95 |

Virheet, joihin sovelluksen pitää varautua: `410` istunto päättynyt (avaa uusi), `429` täynnä tai jono täynnä (odota `Retry-After`), `503` tyhjentyy, ei työläisiä tai lause odotti liian kauan (`waited_too_long`: myöhästynyttä puhetta ei kannata soittaa).

```bash
KEY=$(python3 -c "import json;print(json.load(open('$HOME/f5fi-tila/avaimet.json'))['interactive'])")
URL=$(python3 -c "import json;print(json.load(open('$HOME/f5fi-tila/current.json'))['url'])")
SID=$(curl -s -X POST -H "Authorization: Bearer $KEY" $URL/sessions | python3 -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -s -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
     -d "{\"voice\":\"jooseppi\",\"emotion\":\"iloinen\",\"text\":\"Tervetuloa, istu vain.\",\"session_id\":\"$SID\"}" $URL/speak -o puhe.wav
```

Omat erä-ajot käyttävät `batch`-avainta: ei istuntoa, jono on pidempi, ja Rooliharjoittelun lauseet ohittavat erän lauseet. Prioriteetti toimii lauseen tarkkuudella, joten Rooliharjoittelu odottaa pahimmillaan yhden erän lauseen valmistumista.

### Rooliharjoittelun käyttö

`scripts/f5client.py` hoitaa osoitteen luvun, istunnon ja sydämenlyönnin (vain `httpx` tarvitaan; tiedoston voi kopioida sovellukseen):

```python
addr = f5client.read_address(".../f5fi-tila/current.json")
if addr is None: ...                    # puhepalvelu ei käytössä: tekstitila tai ilmoitus
try:
    with f5client.Client(addr["url"], key).session() as s:
        for lause in llm_lauseet:       # yksi lause kerrallaan: ensimmäinen kuuluu heti, kun se on valmis
            wav, info = s.speak(ääni, lause, tunne)
except f5client.ServiceBusy as e:       # kaikki paikat käytössä: näytä jonotus, yritä uudelleen e.retry_after s päästä
    ...
```

- **LLM palauttaa rakenteen** `{ääni, tunne, teksti}`. Tuntematon tunne korvataan äänen oletustunteella (`X-Emotion` kertoo käytetyn), tuntematon ääni on virhe.
- **Kehotteeseen:** kirjoita luvut ja lyhenteet sanoina ("kello kymmenen", ei "10:30"), koska palvelu ei muuta numeroita. Palvelu poistaa itse `*huokaisee*`, `[naurahtaa]`, hymiöt ja markdownin, mutta ohje säästää tilaa.
- **Kieliopilliset säännöt** (esim. "tervetuloa" → "tervettuloa") tekee palvelu (`f5fi.normalize_text` Voikolla); LLM:n ei tarvitse eikä pidä tehdä niitä. Puhekieltä Voikko ei tunne, joten sen kahdennuksia ei merkitä.
- **Pitkä vuoro:** enintään 8 lausetta ja 600 merkkiä per pyyntö.

## 6. Kapasiteetti ja mittaus

Istuntojen enimmäismäärää (`--max-sessions`) ei voi laskea etukäteen, koska generointiaika lausetta kohden ei ole tiedossa. Arvio kuuluu näin: jos lause kestää `g` sekuntia, vuorossa on keskimäärin `s` lausetta ja vuoroja tulee `T` sekunnin välein, yksi istunto käyttää `s·g/T` työläisen ajasta. Esimerkki (luvut keksittyjä, ei mitattuja): g = 1,5 s, s = 2, T = 15 s → 0,2 työläistä per istunto; kahdella työläisellä ja korkeintaan 50 % käyttöasteella (jotta jono pysyy lyhyenä) mahtuu noin 5 istuntoa.

Mittaa oikeasti, kun palvelu on käynnissä:

```bash
python scripts/serve_bench.py --state-dir ~/f5fi-tila --key-file ~/f5fi-tila/avaimet.json \
       --voice jooseppi --sessions 4 --turns 6 --think-s 8
```

Kasvata `--sessions`-lukua, kunnes äänen valmistumisajan p95 ylittää sen, minkä hyväksyt (puhutulle vastaukselle 1,5–2 s on kohtuullinen raja). Viimeinen hyvä luku on `--max-sessions`. Kokeile myös `F5SERVE_WORKERS` 1, 2 ja 3: jos yksi lause ei kyllästä A30:tä, useampi työläinen kasvattaa läpäisykykyä; jos kyllästää, ei. Jokainen työläinen lataa kaikki mallit (noin 3 Gt), ja muistia rajataan (`--gpu-fraction`).

Palvelu suojaa itseään kahdella tasolla: paikkojen enimmäismäärä ja **mukautuva sisäänotto** (ei uusia istuntoja, kun viimeisen minuutin jonotus ylittää rajan). Jos GPU on hitaampi kuin odotettiin, jälkimmäinen pitää palvelun reaaliaikaisena, vaikka `--max-sessions` olisi asetettu liian suureksi.

Lisäksi, jos reaaliaikaisuus ei riitä: `nfe 16` on noin kaksi kertaa nopeampi kuin oletus 32, mutta sen laatua ei ole kuunneltu. Äänitteen `ref`-pituus kasvattaa laskentaa joka lauseella (generoitava jakso on viite + teksti), joten lyhyt viite on nopeampi.

## 7. Tunnetut rajoitteet ja riskit

- **Siemenet eivät siirry Macilta.** Satunnaislukugeneraattori on laitekohtainen (MPS vs. CUDA), joten Macilla hyväksytty siemen tuottaa palvelimella todennäköisesti eri oton. Kuuntele tunnekohtaiset oletussiemenet uudelleen palvelimella (`serve_bench`/`curl` ja `seed`-kenttä) ja päivitä rekisteri.
- **Ehdokasvalinta (`--candidates`) ei ole mukana.** Se käyttää Applen `mlx-whisper`-kirjastoa eikä sovi reaaliaikaan (kolminkertainen aika).
- **Ei suoratoistoa.** Ääni tulee vasta, kun lause on valmis. Lähetä lauseet yksi kerrallaan LLM:n tulostuessa.
- **Liian pitkään jumittunut työläinen** tapetaan (60 s), ja pyyntö epäonnistuu. Mallit latautuvat sen jälkeen uudelleen (noin 30 s tai enemmän), jolloin kapasiteetti on hetken pienempi.
- **Yksi solmu, yksi GPU.** Jos solmu kaatuu, työ päättyy ja `current.json` vanhenee 45 sekunnissa (ketjutetun työn seuraaja alkaa vasta aikataulunsa mukaan, ei kaatumisesta).
- **HTTP ilman salausta** klusterin sisäverkossa. Pidä portti vain sisäverkossa tai tunneloi se; avaimet kulkevat selkeänä.

## 8. Käyttöehdot ja turva

- `AANI-JA-MALLI.md` kattaa vain Joosepin ja Justiinan. **Justiina2:n ja Valdemarin pitää lisätä** (lupa opetus- ja tutkimuskäyttöön, nimeämistapa). Valdemar on lapsen ääni: tallenna huoltajan lupa kirjallisesti ja selvitä, kuka yliopistolla vastaa äänitteiden ja mallien säilytyksestä (ääni on henkilötietoa).
- Mallin painot ovat CC BY-NC, joten palvelu on tarkoitettu vain opetus- ja tutkimuskäyttöön, ei ulkopuolisille.
- Ohjeen `docs/kaytto-muissa-projekteissa.md` sääntö 3 ("ääni ja malli pysyvät käyttäjän koneella") ei enää pidä paikkaansa palvelinkäytössä: päivitä se tietoisesti.
- Avaimet (`avaimet.json`) ovat vain käyttäjän luettavissa (oikeudet 600); älä kopioi niitä repoon. `.gitignore` estää sen.
- Rajapintaa ei saa avata yleiseen verkkoon: oman äänen kloonaus kenen tahansa kutsuttavaksi on väärinkäytön riski.
