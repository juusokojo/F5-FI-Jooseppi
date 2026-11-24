# Puhepalvelu Lehmuksessa (Slurm)

F5-fi-malli ajetaan palveluna yliopiston GPU-klusterissa (Lehmus, A30 24 Gt) Slurm-työnä. Rooliharjoittelu hakee sieltä lyhyitä puhepurskeita reaaliajassa, ja omat erä-ajot voivat käyttää samaa palvelua matalammalla prioriteetilla.

```
Rooliharjoittelu ──lukee──> ~/.f5-palvelu/osoite.json, avain  <──kirjoittaa── serve.py (sbatch-työ, A30)
        │                                                                       │ portinvartija: jono, lauseet
        └──────── HTTP: GET /health, POST /synthesize (solmu:portti) ──────────┤
                                                                                └─ työläinen: Jooseppi-malli + Valdemar-malli
```

## Mitä on testattu ja mitä ei

| Osa | Tila |
|---|---|
| Rajapinta (`/health`, `/synthesize`), tiedostojen muoto ja oikeudet, virhekoodit, jono, aikakatkaisut, työläisen kaatuminen | Testattu (`tests/test_serve.py`, valetaustalla) |
| Signaalit (SIGTERM, SIGUSR1), osoitteen kirjoitus ja poisto, seuraajalle luovutus | Testattu oikeana prosessina ja oikeilla signaaleilla |
| Asennus (`slurm/install.sh`: Python 3.13, Voikko lähdekoodista ilman root-oikeuksia) | Ajettu läpi Ubuntu-koneella, 118 testiä läpi. `conda`-haara ja Lehmuksen käyttöjärjestelmä testaamatta |
| GPU-koe (`probe.sbatch`) | **Ajettu Lehmuksessa**: lehmus-cn3, A30 24 Gt, ajuri 595.71.05, PyPI ja Hugging Face tavoitettavissa solmulta, kirjautumissolmu pääsee solmun porttiin |
| **Todellinen synteesi GPU:lla** (`F5Backend`) | **Ei testattu.** Ensimmäinen ajo Lehmuksessa on sen koe |
| `serve.sbatch`, `install.sbatch` | Syntaksi tarkistettu, ei ajettu Slurmilla |
| Nopeus ja yhtä aikaa kestävien käyttäjien määrä | **Tuntematon**, mitataan `serve_bench.py`:llä |

## 1. Sopimus Rooliharjoittelun kanssa

**Tiedostot** (kansio `~/.f5-palvelu`, oikeudet 700; tiedostot 600):

- `osoite.json`: `{"url": "http://<solmu>:<portti>", "job": <työnumero>, "started": "<aika>"}`. Palvelu valitsee vapaan portin ja kirjoittaa tiedoston **vasta, kun mallit on ladattu ja lämmitetty** (`/health` vastaa silloin `ok: true`). Sammuessaan se poistaa tiedoston (ei kuitenkaan seuraajansa tiedostoa).
- `avain`: satunnainen avain, pelkkä merkkijono ilman rivinvaihtoa. **Uusi jokaisella käynnistyksellä**, joten lue avain aina samalla kun osoite. Avainta ei poisteta sammuttaessa.

**`GET /health`** (ei avainta): `{"ok": true, "voices": ["jooseppi", "justiina", "justiina2", "valdemar"], "queue": <n>}`. `queue` on jonossa odottavien lauseiden määrä. `ok` on epätosi (503), kun palvelu lataa, tyhjenee tai ei ole työläisiä.

**`POST /synthesize`**, otsake `Authorization: Bearer <avain>`, runko:

```json
{"voice": "justiina2", "clip": "tunne_artynyt_a", "text": "...", "seed": 1}
```

→ `audio/wav` (mono, 16 bit, 24 kHz). Otsakkeet kertovat mm. `X-Seed`, `X-Wait-S` (jonotus) ja `X-Gen-S` (generointi).

| Tilanne | Vastaus |
|---|---|
| Väärä tai puuttuva avain | `401` `{"error": "..."}` |
| Tuntematon ääni tai viite, virheellinen JSON, puuttuva kenttä, tyhjä tai liian pitkä teksti | `400` `{"error": "..."}` (virheilmoitus kertoo, mitä on olemassa) |
| Jono täynnä, tai lause odotti yli 10 s | `503` + `Retry-After`, `{"error": "..."}` |
| Palvelu käynnistyy tai ei ole valmis | `503` + `Retry-After` |
| Synteesi epäonnistui | `500` `{"error": "..."}` |

Muut säännöt:

- **`clip`** on viiteäänitteen nimi (`tunne_artynyt_a`), ja se valitsee äänitteen **ja** äänen tunteen. Tuntematon nimi on virhe (ei oletusta). Nimet tulevat rekisteristä (`slurm/voices.json`, katso kohta 2).
- **`seed`** valinnainen. Ilman sitä käytetään viitteen oletussiementä (rekisterissä, oletus 1).
- **Teksti**: yhdestä neljään lausetta, enintään 600 merkkiä. Palvelu jakaa tekstin lauseiksi (kuten `read_text.py`), generoi ne erikseen ja liittää 0,3 s tauolla. Pidempi teksti on `400`, koska jono ei mahtuisi koskaan sisään.
- **Tekstin normalisointi tehdään palvelussa** Voikolla (rajageminaatio: "tervetuloa" → "tervettuloa", pieni alkukirjain, kaksoispisteen jako). Sovellus lähettää tavallista kirjoitettua suomea. Palvelu myös poistaa `*huokaisee*`, `[naurahtaa]`, hymiöt ja markdownin. Lukuja ja lyhenteitä se **ei** muuta sanoiksi: pyydä LLM:ää kirjoittamaan ne sanoina.
- **Yksi työläinen, lyhyt jono** (oletus 4 lausetta). Palvelu ei tee istuntoja: sovellus päättää itse, montako keskustelua se päästää sisään (ks. kohta 5).

**Sovelluksen pitää kestää nämä** (vähimmäisvaatimukset):

1. Yhteysvirheessä tai aikakatkaisussa **lue `osoite.json` ja `avain` uudelleen** ja yritä kerran. Työ voi olla vaihtunut (aikaraja, seuraaja), ja avain on silloin uusi. Jos tiedostoa ei ole, palvelu ei ole käynnissä: näytä tekstitila tai ilmoitus.
2. `503` on tilapäinen: odota `Retry-After` ja yritä uudelleen, tai ilmoita käyttäjälle jonosta. Myöhästynyttä puhetta ei kannata soittaa.
3. `osoite.json` voi jäädä jäänteeksi, jos työ tapetaan väkivalloin (solmu kaatuu). `GET /health` kertoo, onko osoitteessa oikeasti palvelu.

## 2. Asennus

Kaikki ajetaan `sbatch`-työnä (`srun --pty` ei toimi).

```bash
module load conda                     # tai PYTHON=/polku/python3.13
sbatch slurm/install.sbatch           # ajetaan repositorion juuresta; loki: f5fi-asennus-<työ>.log
```

Skripti (`slurm/install.sh`) tekee ilman root-oikeuksia:

- luo Python 3.13 -ympäristön (`.env-lehmus`) ja asentaa lukitustiedoston paketit ilman `mlx*`-paketteja (ne ovat vain Macille). PyPI:n `torch` on CUDA 13.2 -käännös, ja ajuri 595 riittää siihen;
- **rakentaa Voikon kotihakemistoon** (`~/voikko`): `libvoikko` lähdekoodista (tarvitsee `g++` ja `make`) ja sanakirjan Ubuntun `voikko-fi`-paketista, joka puretaan Pythonilla. Lopuksi se tarkistaa, että "Tervetuloa" muuttuu muotoon "Tervettuloa". **Ilman Voikkoa palvelu kieltäytyy käynnistymästä**, koska säännöt jäisivät hiljaa pois;
- luo tilakansion (`~/.f5-palvelu`) ja erä-avaimen omille ajoille (`avaimet.json`).

Voikon lähteet haetaan `archive.ubuntu.com`-palvelimelta. Kokeessa raportoitiin vain PyPI ja Hugging Face, joten tarkista, tavoittaako solmu myös sen. Jos ei, lataa kaksi tiedostoa omalla koneellasi ja anna ne asennukselle (`VOIKKO_SRC_TARBALL=/polku/libvoikko_4.3.2.orig.tar.gz`, `VOIKKO_FI_DEB=/polku/voikko-fi_2.5-1build1_amd64.deb`):

- `http://archive.ubuntu.com/ubuntu/pool/main/libv/libvoikko/libvoikko_4.3.2.orig.tar.gz`
- `http://archive.ubuntu.com/ubuntu/pool/main/v/voikko-fi/voikko-fi_2.5-1build1_amd64.deb`

**Painot, äänitteet ja rekisteri** (eivät ole repossa):

1. Kopioi `checkpoints/oma-v1/malli_002000.safetensors` (Jooseppi; aikuisten äänten yhteinen malli) ja Valdemarin hienosäätö, esimerkiksi `checkpoints/valdemar-v1/...`.
2. Kopioi `base/`-kansion sanasto (`vocab.txt`) ja Vocos-vokooderi (`~/.cache/huggingface`). Hugging Face tavoitetaan solmulta, joten vokooderin voi myös ladata siellä (koodi käyttää oletuksena `HF_HUB_OFFLINE=1`, joten lataus tehdään kerran erikseen `HF_HUB_OFFLINE=0`). Sen testaamaton esimerkki: `HF_HUB_OFFLINE=0 .env-lehmus/bin/python -c "from huggingface_hub import snapshot_download as d; d('charactr/vocos-mel-24khz')"`. Varmin tapa on kopioida välimuisti Macilta.
3. Kopioi viiteäänitteet kansioon `<kansio>/<ääni>/<viite>.wav` ja jokaisen viereen `<viite>.txt`, jossa on viitteessä sanottu teksti. Tiedostonimi on `clip`-nimi.
4. Kokoa rekisteri:

```bash
.env-lehmus/bin/python slurm/make_registry.py --refs-dir data/viite/palvelu \
    --ckpt valdemar=checkpoints/valdemar-v1/malli_002000.safetensors
```

Skripti kirjoittaa `slurm/voices.json`:n (gitignoressa). Äänet ilman `--ckpt`-valintaa käyttävät Jooseppi-mallia, ja siemen on oletuksena 1. Muokkaa tiedostoa käsin, jos jollakin viitteellä on parempi oletussiemen tai `nfe`. Palvelu tarkistaa käynnistyessään, että jokainen viite, litteraatti ja checkpoint on olemassa, ja lämmittää jokaisen äänen yhdellä lauseella: viallinen tiedosto kaataa käynnistyksen eikä ensimmäistä pyyntöä.

## 3. Käynnistys ja elinkaari

```bash
sbatch slurm/serve.sbatch
squeue -u $USER                       # odota RUNNING
cat ~/.f5-palvelu/osoite.json         # ilmestyy, kun palvelu on valmis
```

Tarkista ennen ensimmäistä ajoa `sinfo -o "%P %G %l"`: osion nimi ja GPU:n nimi (`--partition=interactive`, `--gres=gpu:a30:1`) ovat `serve.sbatch`:ssa arvauksia.

| Tapahtuma | Mitä palvelu tekee |
|---|---|
| Käynnistys | Lataa mallit ja lämmittää ne, **kirjoittaa avaimen ja osoitteen vasta sitten** |
| `scancel` tai aikaraja (SIGTERM) | Jo jonossa olevat lauseet valmistuvat (enintään 15 s, Slurm tappaa 30 s kuluttua), `osoite.json` poistetaan, poistuu koodilla 0 |
| SIGUSR1 (15 min ennen aikarajaa) | Kirjaa varoituksen; jos seuraaja on jo valmis, siirtyy tyhjennystilaan |
| Seuraaja valmistuu | Vanha instanssi vastaa vielä pyyntöihin ja sammuu, kun 20 s on kulunut viimeisestä pyynnöstä. Tämän aikana sovellus ehtii lukea uuden osoitteen |
| Työläinen kaatuu tai jumittuu yli 60 s | Prosessi tapetaan ja käynnistetään uudelleen (enintään 3 kertaa), pyyntö saa virheen |
| Joutilaana (`F5SERVE_IDLE_EXIT_S`) | Valinnainen: sammuu ja vapauttaa GPU:n |

**Viikon rajan ylitys.** `interactive`-osion aikaraja on 7 vrk. Asetuksella `F5SERVE_RESUBMIT=1` jokainen työ tilaa seuraajansa alkamaan 45 min ennen omaa päättymistään; seuraaja ottaa osoitteen heti valmistuttuaan. Oletus on pois, koska ketju varaa GPU:n jatkuvasti. Ketju katkaistaan komennoilla `touch ~/.f5-palvelu/STOP` ja `scancel --name=f5fi-puhe`. Jos seuraaja joutuu jonoon, syntyy katko (sovelluksen kohta 1 kattaa tämän).

**Kysy ylläpidolta:** sopiiko viikon mittainen GPU-varaus palveluksi `interactive`-osiossa, vai pitäisikö käyttää `normal`-osiota (14 vrk) tai erillistä palveluosiota. A30 on 24 Gt. Painot ovat noin 1,4 Gt per malli ja työläinen lataa kaksi mallia, joten muistia kuluu todennäköisesti vain osa; mittaa `nvidia-smi`llä ajon aikana. Jos klusterissa on MIG-osioita (A30 jakautuu enintään neljään 6 Gt:n osaan), pienempi osa voisi riittää.

## 4. Käyttö ja erä-ajot

```bash
D=~/.f5-palvelu; URL=$(python3 -c "import json;print(json.load(open('$D/osoite.json'))['url'])"); KEY=$(cat $D/avain)
curl -s $URL/health
curl -s -H "Authorization: Bearer $KEY" -d '{"voice":"justiina2","clip":"neutraali","text":"Tervetuloa, istu vain.","seed":1}' \
     $URL/synthesize -o puhe.wav
```

Omat erä-ajot käyttävät erä-avainta (`avaimet.json`, kenttä `batch`) samalle `/synthesize`-rajapinnalle. Erä-avaimella on pidempi jono (64 lausetta) ja 5 000 merkin tekstit, ja Rooliharjoittelun lauseet ohittavat erän lauseet jonossa. Prioriteetti toimii yhden lauseen tarkkuudella, joten Rooliharjoittelu odottaa pahimmillaan yhden erän lauseen valmistumista. Rooliharjoittelun oma avain on aina reaaliaikainen.

## 5. Kapasiteetti ja mittaus

Montako keskustelua voi olla yhtä aikaa, ei ole laskettavissa etukäteen, koska lauseen generointiaika `g` ei ole tiedossa. Arvio: jos vuorossa on keskimäärin `s` lausetta ja vuoroja tulee `T` sekunnin välein, yksi keskustelu käyttää `s·g/T` työläisen ajasta. Esimerkki (luvut keksittyjä, ei mitattuja): g = 1,5 s, s = 2, T = 15 s → 0,2 työläistä per keskustelu; yhdellä työläisellä ja enintään 50 % käyttöasteella (jotta jono pysyy lyhyenä) mahtuu noin 2–3 keskustelua.

Mittaa, kun palvelu on käynnissä:

```bash
python scripts/serve_bench.py --voice justiina2 --clip neutraali --users 3 --turns 6 --think-s 8
```

Kasvata `--users`-lukua, kunnes äänen valmistumisajan p95 ylittää sen, minkä hyväksyt (puhutulle vastaukselle 1,5–2 s on kohtuullinen raja). Viimeinen hyvä luku on **sovelluksen sallima samanaikaisten keskustelujen enimmäismäärä**: sovellus rajaa sen itse ja jonottaa tai hylkää ylimääräiset (`/health.queue` ja `503` kertovat kuormasta). Kokeile myös `F5SERVE_WORKERS=2`: jos yksi lause ei kyllästä A30:tä, toinen työläinen kasvattaa läpäisykykyä; jokainen työläinen lataa kaikki mallit. Jos GPU on hitaampi kuin odotettiin: `nfe 16` on noin kaksi kertaa nopeampi, mutta sen laatua ei ole kuunneltu, ja viiteäänitteen pituus kasvattaa laskentaa joka lauseella (generoitava jakso on viite + teksti).

## 6. Lisärajapinta (ei pakollinen)

Palvelussa on myös laajempi rajapinta, jota Rooliharjoittelun sopimus ei vaadi: istuntopaikat (`POST /sessions`, heartbeat) ja mukautuva sisäänotto, `/speak` (tunnenimi, jolla on oletusarvo, tuntemattomalle tunteelle), `/voices`, `/status` ja `scripts/f5client.py`. Ne ovat testattuja (`tests/test_serve.py`), mutta niitä ei tarvita, jos sovellus rajaa keskustelut itse.

## 7. Tunnetut rajoitteet ja riskit

- **Siemenet eivät siirry Macilta.** Satunnaislukugeneraattori on laitekohtainen (MPS vs. CUDA), joten Macilla hyväksytty siemen tuottaa palvelimella todennäköisesti eri oton. Kuuntele viitteiden oletussiemenet uudelleen palvelimella ja päivitä rekisteri.
- **Ehdokasvalinta (`--candidates`) ei ole mukana**: se käyttää Applen `mlx-whisper`-kirjastoa eikä sovi reaaliaikaan (kolminkertainen aika).
- **Ei suoratoistoa.** Ääni tulee vasta, kun lause on valmis. Lähetä lauseet yksi kerrallaan, jos haluat ensimmäisen kuuluviin nopeammin.
- **Yksi solmu, yksi GPU.** Jos solmu kaatuu, työ päättyy. `osoite.json` jää jäänteeksi ja ketjutetun työn seuraaja alkaa vasta aikataulunsa mukaan.
- **HTTP ilman salausta** klusterin sisäverkossa. Pidä portti vain sisäverkossa; avain kulkee selkeänä, ja se on uusi joka käynnistyksessä.

## 8. Käyttöehdot ja turva

- **Valdemar** (lapsen ääni) ja **Justiina2** on lisätty tiedostoon `AANI-JA-MALLI.md` (24.11.2026), ja siinä on erikseen mainittu, että äänet ja mallit saa käyttää ja ajaa yliopiston palvelimilla Oulun yliopiston opetus- ja tutkimusprojekteissa. Selvitä silti, kuka yliopistolla vastaa äänitteiden ja mallien säilytyksestä (ääni on henkilötietoa) ja ketkä palvelimella pääsevät niihin käsiksi.
- Mallin painot ovat CC BY-NC: palvelu on vain opetus- ja tutkimuskäyttöön, ei ulkopuolisille.
- Ohjeen `docs/kaytto-muissa-projekteissa.md` sääntö 3 on päivitetty: ääni ja malli pysyvät käyttäjän hallinnassa omalla koneella tai yliopiston palvelimella, ja ulkoisille Oulun yliopiston projekteille on oma osio.
- Avaimet ovat vain käyttäjän luettavissa (600), eikä niitä kirjoiteta lokiin eikä repoon (`.gitignore`). Rajapintaa ei saa avata klusterin ulkopuolelle: oman äänen kloonaus kenen tahansa kutsuttavaksi on väärinkäytön riski.
