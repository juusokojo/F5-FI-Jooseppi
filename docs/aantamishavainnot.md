# Ääntämishavainnot kuuntelukokeista

Tämä dokumentti kokoaa, mitä mallin ääntämisestä opittiin, kun Koulutusmateriaalit-projektin mikrokurssin kolmen videon kerronta tuotettiin F5-fi:llä 10.–11.11.2026. Juuso kuunteli kahdeksan korjauskierrosta ja hyväksyi lopuksi kaikki videot. Havaintoja käytetään, kun moduulia `scripts/f5fi.py` kehitetään ja kun mallia hienosäädetään Juuson äänellä.

- **Malli ja asetukset:** perusmalli (`checkpoints/` tyhjä), viite `data/viite/v3/viite_selitys_2`, nfe 32, ehdokkaita 3 ja muut asetukset oletuksina. Jokainen lause tuotettiin erikseen `f5fi.synthesize`-funktiolla.
- **Lähteet (Koulutusmateriaalit-projektissa, ei muokata täältä):** `tuotanto/f5-palaute.md` (havainnot ja mittaukset), `tuotanto/aanitysloki.md` (kierrokset ja Juuson perustelut), `tuotanto/aani/lauseet.json` (hyväksytyt kirjoitusasut ja lähdeotot) ja `tuotanto/aani/korjaustesti/` (koelistat, otot ja kuunneltavat versiot).
- **Vertailuaineisto:** samat otot on kopioitu kansioon `data/vertailu/2026-11-11_koulutusmateriaalit/`. Kuuntelusivu on `index.html`, ja jokaisen oton teksti, siemen ja Juuson päätös ovat tiedostossa `kuvaus.json`. Katso [Vertailuaineisto](#vertailuaineisto-hienosäädetyn-mallin-arviointiin).

Havainnot jakautuvat kahteen ryhmään:

- **A. Tekstin esikäsittelyllä korjattavat** (kohdat 1–7). Mallille annettu kirjoitusasu korjasi virheen, joten korjaus voidaan siirtää moduuliin `scripts/f5fi.py`. Kuuntelukokeen perusteella E2 (kieltomuoto) ja E6 (pieni alkukirjain) otettiin käyttöön 12.11.2026. Muut ehdotukset odottavat Juuson päätöstä, ja jokainen testataan kuuntelukokeella ennen käyttöönottoa (katso [Ehdotetut moduulimuutokset](#ehdotetut-moduulimuutokset)).
- **B. Vain hienosäädöllä tai otto- ja siemenvalinnalla korjattavat** (kohta 8). Lausepaino, fokus ja luettelon intonaatio eivät korjaantuneet tekstiä tai taukoja muuttamalla.

## Yhteenveto

| # | Ilmiö | Ryhmä | Mikä toimi (Juuson kuuntelu) | Moduulissa nyt |
|---|---|---|---|---|
| 1 | Kaksoispisteen jälkeen ei taukoa | A | Lause jaetaan kaksoispisteen kohdalta kahdeksi otoksi, väliin 0,3 s | ei käsittele kaksoispistettä |
| 2 | Rajageminaatio puuttuu sanarajalta | A | Kahdennus kirjoitettuna: ”kannatas”, ”kirjoittaas”, ”päättäät”, ”kysyk” | 1. infinitiivi ja kieltomuoto (kieltomuoto 12.11.2026 alkaen) |
| 3 | Rajakohta vokaalin edellä (”tarvitse ymmärtää”) | A | h-kirjain: ”tarvitseh ymmärtää”, ”ymmärtääh itse”, ”osatah itse” | ohittaa vokaalilla alkavat sanat; yleissääntö hylättiin sokkokokeessa |
| 4 | Pilkun kohdalla pisteen kaltainen tauko | A ja B | Pilkku pois mallin tekstistä ennen sivulausetta; tauot ≤ 0,15 s jälkikäsittelyssä, mutta ei kaikissa lauseissa | ei käsittele |
| 5 | ”pitopalveluyrittäjä”: y katoaa | A | Tavuviiva: ”pitopalvelu-yrittäjä” | ei käsittele |
| 6 | Lauseen alun äänne vaihtuu (”viittää”, ”Kutkijat”) | A | Lauseen alkukirjain pienellä: ”riittää”, ”asiakkaiden” | pienentää alkukirjaimen 12.11.2026 alkaen |
| 7 | Kahdennus puuttuu yhdyssanan sisältä (”saatetekstin”) | A | Kahdennus kirjoitettuna: ”saatettekstin” | käsittelee vain sanarajoja |
| 8 | Lausepaino ja luettelon intonaatio | B | Siemenvalinta korvalla (8 ottoa), luettelossa lisäksi pilkku ennen ja-sanaa | ei voi käsitellä |

Kierrosten numerot viittaavat äänityslokin korjaustesteihin 1–8.

## A. Tekstin esikäsittelyllä korjattavat

### 1. Kaksoispisteen jälkeen ei tule taukoa

**Ilmiö.** Malli lukee kaksoispisteen yli ilman taukoa. Juuson mukaan kaksoispisteen jälkeen kuuluu pieni tauko.

| Lause | Tauko kaksoispisteessä | Vertailu |
|---|---|---|
| V1-07-s3 ”Käytännössä esität itsellesi kysymyksiä: Miksi käytän tekoälyä juuri tässä?” | 0–0,05 s | – |
| V1-02-s1 ”Ensimmäinen on ammattitaito: oman alan, asiakkaiden ja oman yrityksen tuntemus.” | 0–0,05 s | pilkku ”alan,” 0,26 s |

Mittaus tehtiin raa'asta mallin tuotoksesta (hiljaisuus −40 dB, vähintään 0,05 s). Jälkikäsittely ei aiheuttanut ilmiötä, koska se leikkaa hiljaisuutta vain lauseen alusta ja lopusta.

| Kokeiltu keino | Tulos |
|---|---|
| Lause jaetaan kaksoispisteen kohdalta kahdeksi otoksi, ja osat liitetään 0,3 s tauolla (kierros 1, `05a`) | **hyväksytty.** Juuson mukaan ”Käytännössä” kuulosti täydelliseltä. |
| ”Toinen kohta: tekoälyosaaminen.” yhtenä lauseena (kierros 1, `04a`) | ei valittu. Pisteellä jaettu ”Toinen kohta.” + 0,35 s + ”Tekoälyosaaminen.” valittiin. |

**Päätelmä.** Kaksoispiste toimii samoin kuin lauseen raja: osat tuotetaan erikseen ja liitetään lyhyellä tauolla. Toisen osan alkukirjain on silloin iso (”Miksi”), joten kohdan 6 alkukirjainsääntö koskee myös sitä.

### 2. Rajageminaatio jäi pois sanarajalta

**Ilmiö.** Perusmalli ei tuota rajageminaatiota itse. `rajageminaatio.py` merkitsee vain 1. infinitiivin hallitsevan verbin jälkeen (välissä ei välimerkkiä) ja passiivin kieltomuodon. Juuso vahvisti puuttuvan kahdennuksen kohdissa V1-03-s1, V1-05-s3 ja V1-06-s2.

| Lause | Kohta | Miksi moduuli ei merkinnyt |
|---|---|---|
| V1-03-s1 | ”voi ehdottaa …, kirjoittaa saatetekstin” → kirjoittaas | Infinitiivi luettelossa pilkun jälkeen. Hallitseva verbi on ennen pilkkua. |
| V1-05-s3, V1-06-s2 | ”ei kannata syöttää” → kannatas | Aktiivin kieltomuoto (konnegatiivi) ei ole käytössä. |
| V2-04-s1 | ”ei ole tehdä” → olet | Sama kuin edellä. |
| V2-04-s2 | ”tavoitteena on päättää tietoisesti” → päättäät | Hallitsevana on rakenne ”tavoitteena on”, ei verbiluettelon verbi. |
| V3-02-s1 | ”kysy kolme asiaa” → kysyk | Yksikön 2. persoonan imperatiivi on pois päältä. |

| Kokeiltu keino | Tulos |
|---|---|
| ”kirjoittaas”, ”kannatas” kirjoitettuna (kierros 1, `03a`, `03d`) | **hyväksytty** |
| ”päättäät”, ”kysyk” (kierros 5, c-versiot) | **hyväksytty** (samassa otossa myös pieni alkukirjain) |
| ”ei olet tehdä” (kierros 5) | **ei valittu.** Juuso valitsi merkitsemättömän alkuperäisen oton, jonka tauot oli lyhennetty. Ainoa merkitty kohta, joka ei voittanut. |
| ”kirjoittaass”, ”ssaatetekstin” (kierros 3) | ei valittu |

**Imperatiivi.** Moduulissa imperatiivi on pois päältä, koska 6.11. kuuntelukokeessa ”Älä mene sinne, vaan tule tänne” kuulosti merkittynä luonnottomalta. Nyt myönteinen imperatiivi ilman kieltoa ja vastakohtaa (”kysyk kolme asiaa”) hyväksyttiin. Aiempi koe ei siis koske kaikkia imperatiiveja.

**Sivuhavainto: käsin merkitty sana katkaisee moduulin merkinnän.** Voikko ei tunne käsin kirjoitettua muotoa ”kannatas”. Siksi moduuli ei enää tunnista sitä hallitsevaksi verbiksi, ja seuraava kahdennus jää merkitsemättä: ”ei kannata syöttää palveluun” → moduuli: ”syöttääp palveluun”, mutta ”ei kannatas syöttää palveluun” → ”syöttää palveluun”. Hyväksytystä V1-06-s2:sta puuttuu siksi kahdennus ”syöttääp palveluun”, eikä Juuso huomannut sitä. Korjaukset kannattaa tehdä moduulissa eikä käsin, jotta kaikki kohdat merkitään.

**Voikko ja kieltomuoto.** Voikko analysoi kieltomuodot ”kannata”, ”tarvitse”, ”ole” ja ”pysty” yksikön 2. persoonan imperatiiviksi (`MOOD=imperative`, `NEGATIVE=both`). Kieltomuodon tunnistaa siitä, että edellä on kieltoverbi (”ei”, ”en”, ”et”, ”emme”, ”ette”, ”eivät”).

### 3. Rajakohta vokaalin edellä: ”tarvitseh ymmärtää”

**Ilmiö.** Juuson mukaan sanojen ”tarvitse” ja ”ymmärtää” väliin kuuluisi jotain, ja nyt ne liimautuvat yhteen. Ilmiö on sama kuin rajageminaatio: vokaalin edellä se toteutuu kurkkusulkeumana [ei tarvitseʔ ymmärtää]. `rajageminaatio.py` ohittaa vokaalilla alkavat sanat (`CONSONANTS`-tarkistus).

| Kokeiltu keino (V1-05-s2 ”Kielimallin rakentamista ei tarvitse ymmärtää.”) | Tulos |
|---|---|
| heittomerkki ”tarvitse' ymmärtää” (kierros 1) | hylätty |
| pilkku ”tarvitse, ymmärtää” (kierros 1) | hylätty |
| viiva ”tarvitse - ymmärtää” (kierros 1) | hylätty |
| ”tarvitsek ymmärtää” (kierros 2) | hylätty |
| kaksi ottoa, välissä katko 0,06 s tai 0,12 s (kierros 2) | hylätty |
| **”tarvitseh ymmärtää”** (kierros 2, `07b`) | **hyväksytty** |

Sama h-merkintä hyväksyttiin kierroksella 5 kolmessa muussa lauseessa:

- V2-02-s2 ”voi … vähentääh oman ymmärryksen”
- V3-02-s2 ”mitä minun pitää tässä ymmärtääh itse?”
- V3-02-s4 ”mitä haluan jatkossakin osatah itse?”

Näissä kolmessa laukaisija on hallitsevan verbin (”voi”, ”pitää”, ”haluan”) jälkeinen 1. infinitiivi, jonka moduuli jo tunnistaa. Merkintä jäi tekemättä vain siksi, että seuraava sana alkaa vokaalilla.

Muita samanlaisia kohtia kerronnassa: V1-04-s1 ”ei pysty arvioimaan”. Juuso ei maininnut sitä.

### 4. Pilkun kohdalla liian pitkä, pisteen kaltainen tauko

**Ilmiö.** Pilkkujen kohdalla mallin tauot olivat 0,22–0,38 s. Pisimmät olivat ”varmana, esimerkiksi” (0,38 s) ja ”miettimättä, käytetäänkö” (0,36 s). Jälkimmäisessä Whisper litteroi pilkun pisteeksi, joten malli teki kohtaan myös lauseen lopun laskevan sävelkulun. Ilmiö on osin prosodinen (ryhmä B).

| Kokeiltu keino | Lause | Tulos |
|---|---|---|
| Pilkku pois mallin tekstistä ennen sivulausetta (`03d`) | V1-06-s2 ”miettimättä käytetäänkö” | **hyväksytty** |
| Pilkku ennallaan, tauot lyhennetty jälkikäsittelyssä enintään 0,15 s (`03c`) | V1-06-s2 | ei valittu |
| Lauseen sisäiset tauot enintään 0,15 s (`06a`) | V1:n kaikki lauseet | **hyväksytty** (kierros 1) |
| Tauko ennen ”esimerkiksi” 0,15 / 0,25 / 0,37 / 0,50 s (kierros 4) | V1-06-s1 ”varmana, esimerkiksi” | **0,25 s hyväksytty.** Juuso korjasi aiemman mielipiteensä: pilkku ja pieni painotus ovat tarpeen, koska perään tulee luettelo. |
| Pilkku pois (kierros 3) | V1-06-s1 | ei valittu |
| Mallin omat tauot vs. lyhennetyt (kierros 5) | V2-01-s1 ”säästää aikaa, ja aika on …” | **mallin omat tauot hyväksytty** (`noCap`) |
| Sama (kierros 5) | V3-01-s1 | Juuso ei kuullut eroa. |

**Päätelmä.** Kiinteä taukosääntö ei toimi kaikissa lauseissa. Lyhennys enintään 0,15 sekuntiin paransi useimpia lauseita, mutta päälauseiden välinen pilkku (”aikaa, ja aika”) ja luetteloa edeltävä pilkku (”varmana, esimerkiksi”) tarvitsivat pidemmän tauon. Pilkun poisto mallin tekstistä auttoi silloin, kun pilkun kohdalle tuli lopun lasku. Lopullinen ratkaisu on, että malli oppii hienosäädössä Juuson tavan tauottaa (ryhmä B).

### 5. ”pitopalveluyrittäjä”: y-kirjain katoaa

**Ilmiö.** Malli nielaisee y:n, ja sana kuulostaa muodolta ”pitopalvelurittäjä”. Whisper kuuli saman kaikissa otoissa. Todennäköinen syy on u + y -vokaaliyhtymä yhdyssanan rajalla (”-palvelu|yrittäjä”).

| Kokeiltu keino (V1-02-s2 ”Leena on pitopalveluyrittäjä.”) | Tulos |
|---|---|
| **tavuviiva ”pitopalvelu-yrittäjä”** | **hyväksytty** |
| erikseen ”pitopalvelu yrittäjä” | hylätty |
| kaksi y:tä ”pitopalveluyyrittäjä” | hylätty |

**Avoin kysymys.** Ei tiedetä, koskeeko ilmiö kaikkia yhdyssanoja, joissa alkuosa päättyy vokaaliin ja jälkiosa alkaa vokaalilla. Samassa kerronnassa ”tekoälyosaaminen” (y|o) kuului Whisperille muotona ”tekoa lyosaaminen”, mutta Juuso ei maininnut sitä. ”Yhteistyöosaamiseksi” (ö|o) kuului oikein.

### 6. Lauseen alun äänne vaihtuu, kun alkukirjain on iso

**Ilmiö.** Virhe on aina lauseen ensimmäisessä äänteessä:

- ”Riittää” kuului muotona ”viittää” (Whisper kaikilla siemenillä 1–6).
- ”Asiakkaiden” kuului muotona ”äsiakkaiden” tai ”esiakkaiden”.
- ”Tutkijat” → ”Kutkijat”, ”Tutkimuksessa” → ”Kutkimuksessa”, ”Ilmiöstä” → ”Ylmiöstä” ja ”Kolmas kohta” → ”Olmas kohta” (Whisper osalla siemenistä).

| Kokeiltu keino | Tulos |
|---|---|
| **”riittää” pienellä alkukirjaimella** (kierros 2, `08a`) | **hyväksytty.** Whisper kuuli alun oikein kaikilla siemenillä 1–3. |
| ”Rriittää” (`08b`) | hylätty |
| ”Riittää”, siemenet 4–6 (`08c`) | hylätty |
| **”asiakkaiden” pienellä alkukirjaimella** (`09a`) | **hyväksytty** |
| ”Asijakkaiden” (`09b`) | hylätty |
| ”Asiakkaiden”, siemenet 4–6 (`09c`) | ei valittu (siemen 4 kuului Whisperille oikein) |

Kierroksella 5 kaikki uudet otot tehtiin pienellä alkukirjaimella, ja niistä hyväksyttiin kahdeksan lausetta 17:stä. Niissä pieni alkukirjain on kuitenkin samassa otossa muiden muutosten kanssa, joten ne eivät yksinään todista alkukirjaimen vaikutusta.

**Syy on testaamatta.** Virhe voi johtua siirtymästä viitenäytteestä tuotettuun puheeseen, tai iso alkukirjain voi olla harvinainen mallin koulutusaineistossa. Moduuli pienentää jo ison Ä:n, Ö:n ja Å:n, koska ”Älä mene” kuului muotona ”Lämene”. Ilmiö näyttää siis koskevan kaikkia isoja alkukirjaimia.

### 7. Kahdennus yhdyssanan sisällä: ”saatettekstin”

**Ilmiö.** Sanassa ”saatetekstin” kahdennus puuttuu yhdyssanan rajalta, ja sana kuulostaa muodolta ”saate|tekstin”. Oikea ääntämys on [saatettekstin]. Alkuosa ”saate” on e-loppuinen nomini, joka kahdentaa seuraavan konsonantin myös yhdyssanan sisällä, kuten ”perhettuttu” ja ”huonekkalu”. Juuso huomasi tämän vasta kierroksella 3, kun sanarajan kahdennus ”kirjoittaas” oli jo korjattu.

| Kokeiltu keino (V1-03-s1) | Tulos |
|---|---|
| **”saatettekstin”** (kierros 4, `15a`) | **hyväksytty** |
| ”saatet tekstin” erikseen (`15b`) | ei valittu |
| ”saatet-tekstin” tavuviivalla (`15c`) | ei valittu |
| ”saatetekstin”, siemenet 4–6 (`11a`) | ei valittu |

Voikko jakaa yhdyssanan osiin: `saatetekstin` → `WORDBASES = +saate(saate)+teksti(teksti)`. Samoin ”huonekalu” → `+huone+kalu` ja ”perhetuttu” → `+perhe+tuttu`.

## B. Vain hienosäädöllä tai otto- ja siemenvalinnalla korjattavat

### 8. Lausepaino ja luettelon intonaatio

**Ilmiö.** Juuso hylkäsi kierroksilla 5 ja 6 viisi lausetta, vaikka niiden äänteet olivat oikein. Hän kuvasi ilmiöitä ensin tauoiksi, mutta lisätyt tauot eivät auttaneet. Kyse on prosodiasta: malli ei nosta uutta tai kontrastoitavaa tietoa esiin (lausepaino eli fokus), eikä se tee luettelolle jatkuvaa, ei-loppuvaa intonaatiota.

| Lause | Mitä puuttuu | Juuson sanat |
|---|---|---|
| V2-01-s2 ”Pysähdytään silti vaikeampaan kysymykseen.” | Konnektiivi ”silti” kontrastoi edelliseen lauseeseen. Sen jälkeen sävelkorkeus palautuu, ja paino on sanalla ”vaikeampaan”. | ”tauko ei ollut ratkaisu” |
| V2-02-s3 ”Ilmiöstä käytetään nimeä metakognitiivinen laiskuus.” | Uusi termi tarvitsee painon (remaattinen aksentti). | ”vaatii painon sanalle metakognitiivinen”, ”tarvitsee painon, ei taukoa” |
| V2-03-s1 ”Oman ajattelun ohjaaminen toimii siksi kahdella tasolla.” | Fokus on sanalla ”kahdella”, koska kaksi tasoa esitellään seuraavaksi. | ”siksi kahdella: ei toimi” |
| V3-03-s1 ”Tekoäly voi luonnostella, ideoida ja haastaa.” | Luettelon jäsenten rytmi ja sävelkulku ovat epätasaiset. Ja-sanan kohdalle tarvitaan pidempi väli. | ”tauot saavat tekstin pätkimään” |
| V3-03-s2 ”Tavoitteen asettaa, tuloksen arvioi ja päätöksen tekee yrittäjä.” | Sama luettelon ongelma. Pilkku tuottaa lopun kaltaisen laskun; Whisper kuuli pilkun pisteenä (”asettaa. Tuloksen”). | sama |

**Kokeillut keinot, jotka eivät auttaneet** (kierros 6, `r6-*`, ja kierros 8):

- hiljaisuuden lisääminen sanarajalle (0,15 s ja 0,25 s)
- pilkku mallin tekstissä (”silti, vaikeampaan”, ”nimeä, metakognitiivinen”)
- lauseen jakaminen kahdeksi otoksi (”… toimii siksi. [0,2 s] kahdella tasolla.”)
- pilkun poisto luettelosta
- luettelon välien tasaaminen samanpituisiksi (0,12 s)
- ”ideoida ja” -kohdan hidastaminen 12 % tai 20 % ja 0,08 s tauko ennen ja-sanaa (kierros 8)

**Mikä toimi:**

- **Siemenvalinta korvalla (kierros 7).** Samasta tekstistä tuotettiin kahdeksan ottoa siemenillä 4–11, ja Juuso valitsi parhaan. Tämä toimi neljässä lauseessa viidestä: ”silti” (siemen 5), ”metakognitiivinen” (siemen 4), ”siksi kahdella” (siemen 4) ja ”asettaa, tuloksen arvioi ja” (siemen 4).
- **Pilkku ennen ja-sanaa ja siemenvalinta (kierros 8).** Lauseessa ”luonnostella, ideoida ja haastaa” mikään siemen ei riittänyt, koska ja-sana tarvitsi pidemmän välin. Ratkaisu oli antaa mallille teksti ”luonnostella, ideoida, ja haastaa” ja valita siemen 8. Pilkku on vain mallin tekstissä; kirjoitusohjeen mukaan suomessa ei käytetä pilkkua ennen luettelon viimeistä ja-sanaa.

**Whisper ei erota intonaatiota.** Kierroksella 7 Whisperin pisteet olivat lähes kaikissa otoissa 1,0. Automaattinen ehdokasvalinta (`--candidates`) ei siksi löydä parasta intonaatiota. Yksi heikko vihje löytyi: lauseessa V3-03-s2 Whisper kirjoitti siemenillä 5–8 ja 11 pilkun kohdalle pisteen (”asettaa. Tuloksen”) ja siemenillä 4, 9 ja 10 pilkun. Juuson valitsema siemen 4 oli pilkulla litteroitujen joukossa. Litteroinnin välimerkit voisivat siis karsia luettelon pahimmat otot, mutta tätä ei ole testattu.

**Sivuhavainto: j-kahdennus ennen ja-sanaa.** Moduuli merkitsi alkuperäiseen luettelolauseeseen ”ideoidaj ja haastaa”, ja kaikki kierrosten 5–7 otot tehtiin tällä merkinnällä. Hyväksytyssä tekstissä ”ideoida, ja haastaa” pilkku esti merkinnän. On mahdollista, että osa ongelmasta oli j-kahdennuksessa, joka liimaa luettelon jäsenen ja-sanaan. Tätä ei ole testattu. Moduulin 6.11. kokeessa j:n merkinnästä ei kuulunut eroa.

**Miksi hienosäätö.** F5:ssä ei ole tekstimerkintää painotukselle tai intonaatiolle. Siemen arpoo prosodian, joten oikea paino löytyy vain kokeilemalla. Hienosäätö Juuson luennalla voi opettaa mallille, miten Juuso merkitsee fokuksen, konnektiivin ja luettelon. Siksi aineistoon ehdotetaan oma sarja, joka harjoittaa juuri näitä ilmiöitä: [lukulauseet.md, sarja 5](lukulauseet.md#sarja-5-painotus-luettelot-ja-rajakohdat).

## Hienosäätöaineisto ja esikäsittely kuuluvat yhteen

`prepare_dataset.py` vie hienosäätöaineiston tekstit saman esikäsittelyn läpi kuin synteesissä (`metadata.csv`: rajageminaatio ja pienet Ä ja Ö). Kun Juuso lukee lauseet luontevasti, hänen äänitteissään on rajageminaatio ja kurkkusulkeuma myös niissä kohdissa, joita moduuli ei nyt merkitse: kieltomuodon jälkeen, vokaalin edellä ja yhdyssanan sisällä. Silloin teksti ja ääni ovat ristiriidassa: äänessä on kahdennus, tekstissä ei. Malli oppii parhaiten, jos merkintä on johdonmukainen. Siksi moduulin muutoksista kannattaa päättää ennen ensimmäistä hienosäätöä, ja `metadata.csv` kootaan uudelleen (`--rebuild`) muutosten jälkeen.

## Ehdotetut moduulimuutokset

**Tilanne 12.11.2026:** E2 ja E6 ovat **käytössä** Juuson sokkokuuntelun perusteella. E3 on toteutettu, mutta se jäi pois päältä, koska h kuului usein h:na. Katso [Kuuntelukoe E2, E3 ja E6](#kuuntelukoe-e2-e3-ja-e6). Hienosäätöaineiston `metadata.csv` koottiin uudelleen (`--rebuild`), ja 251 tekstiä 273:sta muuttui, lähinnä alkukirjaimen osalta. Myös E1, E4, E5, E7 ja E8 ovat **käytössä** 12.11.2026 alkaen toisen sokkokokeen perusteella (katso [Kuuntelukoe E1, E4, E5, E7 ja E8](#kuuntelukoe-e1-e4-e5-e7-ja-e8)). `metadata.csv` koottiin niiden jälkeen uudelleen, ja 16 tekstiä 273:sta muuttui (esim. ”lues se”, ”kerror rauhassa”, ”tervettuloa”, ”rautatie-asema”). Seurattava: E8 lisää tavuviivan myös vakiintuneisiin sanoihin, kuten ”yli-opiston”, joka sanotaan yleensä yhteen. E9 (siemenvalintatila) ja E10 (taukojen enimmäispituus, valinnainen) on toteutettu 12.11.2026. Testaamatta ovat E11–E14.

Jokainen odottaa Juuson päätöstä, ja jokainen testataan kuuntelukokeella ennen käyttöönottoa, kuten projektissa on tähän asti tehty: sama lause merkittynä ja merkitsemättä, useampi lause ja ilmiö kerrallaan.

| # | Muutos | Peruste | Ehdotettu kuuntelukoe |
|---|---|---|---|
| E1 | **Käytössä 12.11.2026.** **Kaksoispiste:** `synthesize` jakaa lauseen kaksoispisteen kohdalta, tuottaa osat erikseen ja liittää ne 0,3 s tauolla. | Kohta 1: hyväksytty kierroksella 1. | 4–6 lausetta, joissa kaksoispiste on eri asemissa (selitys, luettelo, kysymys). |
| E2 | **Käytössä 12.11.2026.** **Aktiivin kieltomuoto** käynnistää rajageminaation: kieltoverbi + imperatiivin muotoinen sana (”ei kannata syöttää” → kannatas). | Kohta 2: ”kannatas” hyväksytty. Huom.: ”ei olet tehdä” ei voittanut. | Useita kieltolauseita eri verbeillä (kannata, tarvitse, ole, pysty, voi), merkittynä ja merkitsemättä. |
| E3 | **Hylätty 12.11.2026 (pois päältä).** **h vokaalin edellä:** kun laukaiseva muoto edeltää vokaalilla alkavaa sanaa, loppuun lisätään h (”tarvitseh ymmärtää”, ”osatah itse”). Koskee samoja laukaisijoita kuin konsonantin edellä. | Kohta 3: hyväksytty neljässä lauseessa; kaikki muut kirjoitusasut hylättiin. | 6–8 lausetta, myös ”ei pysty arvioimaan” -tyyppiset. Kuuntele erityisesti, ettei h kuulu h:na. |
| E4 | **Käytössä 12.11.2026.** **Hallitseva verbi luettelon yli:** haku jatkuu pilkun yli, kun pilkun jälkeen tulee toinen 1. infinitiivi (”voi ehdottaa …, kirjoittaa saatetekstin”). | Kohta 2: ”kirjoittaas” hyväksytty. | 3–4 luettelolausetta. |
| E5 | **Käytössä 12.11.2026.** Koskee myös *älä*-sanan jälkeistä verbiä (”älä unohdas sammuttaa”). **Myönteinen imperatiivi** uudelleen käyttöön ilman kieltoa ja vastakohtaa (”kysy kolme asiaa” → kysyk). | Kohta 2: ”kysyk” hyväksytty. Aiempi hylkäys koski lausetta, jossa oli kielto ja vastakohta. | Imperatiivilauseita ilman kieltoa ja kieltolauseita rinnakkain. |
| E6 | **Käytössä 12.11.2026.** **Lauseen alkukirjain pieneksi** ennen synteesiä. Erisnimet säilyvät (Voikon sanaluokka). | Kohta 6: hyväksytty kahdessa lauseessa; laajentaa nykyisen Ä/Ö/Å-säännön. | 8–10 lausetta, joiden ensimmäinen äänne on t, r, k, a tai i, isolla ja pienellä, useammalla siemenellä. Vaikuttaa myös `metadata.csv`:hen. |
| E7 | **Käytössä 12.11.2026.** **Kahdennus yhdyssanan sisällä:** Voikon `WORDBASES` jakaa yhdyssanan, ja kun alkuosa on e-loppuinen nomini (saate, perhe, huone), jälkiosan alkukonsonantti kahdennetaan (”saatettekstin”). | Kohta 7: hyväksytty. | 5–6 yhdyssanaa (saateteksti, perhetuttu, huonekalu, kirjekuori, venematka). |
| E8 | **Käytössä 12.11.2026.** **Tavuviiva yhdyssanan vokaalirajalle** (”pitopalvelu-yrittäjä”). | Kohta 5: hyväksytty yhdessä sanassa. Yleistys on epävarma. | Ensin koe 6–8 sanalla, joiden rajalla on vokaaliyhtymä. Otetaan käyttöön vain, jos virhe toistuu. |
| E9 | **Toteutettu 12.11.2026** (`speak.py --seeds`, `f5fi.seed_takes`). **`--seeds`-tila** `speak.py`:hyn ja `f5fi`-moduuliin: jokaisen siemenen otto tallennetaan erikseen kuuntelua varten, ja kuuntelusivu kootaan automaattisesti. | Kohta 8: ainoa keino lausepainoon ennen hienosäätöä. Koulutusmateriaaleissa toteutettu `tools/f5_batch.py --seeds`. | Ei vaadi kuuntelukoetta, koska ei muuta ääntä. |
| E10 | **Toteutettu 12.11.2026, valinnainen** (`speak.py --max-pause`, `--longest-pause`, `f5fi.cap_pauses`). **Taukojen enimmäispituus** valinnaisena asetuksena (esim. `max_pause=0.15`), ei oletuksena. | Kohta 4: paransi useimpia lauseita, mutta ei kaikkia. | Ei tarvita, jos asetus on valinnainen. |
| E11 | **j-kahdennus ennen ja-sanaa luettelossa** pois (”ideoidaj ja”). | Kohta 8, sivuhavainto. Testaamatta. | Luettelolauseet j-merkinnällä ja ilman, samalla siemenellä. |
| E12 | **e-sanan rajageminaatio sanarajalla:** perhe- ja huone-tyyppinen e-sana perusmuodossa kahdentaa myös seuraavan sanan alkukonsonantin (”ruokaohje löytyi” → ”ruokaohjel löytyi”). | Juuson huomio kokeessa 12.11.2026 (E8-5). Sama tunnistus kuin E7:ssä. | Lauseita, joissa e-sana on subjektina tai objektina ennen konsonanttia. |
| E13 | **Kahdentavat seikkasanat**, esimerkiksi ”kiinni kaiteesta” → ”kiinnik kaiteesta”. | Juuson huomio kokeessa 12.11.2026 (E5-4). Voikko ei merkitse tätä, joten tarvitaan sanaluettelo. | Ensin luettelo sanoista, sitten koe. |
| E14 | **Infinitiivi, jolla on myös nominitulkinta:** ”kertoa taustan” jää merkitsemättä, koska Voikko tulkitsee ”kertoa” myös sanan ”kerto” partitiiviksi. Kun sanaa hallitsee verbi tai luettelo, infinitiivitulkinta voisi riittää. | Juuson huomio kokeessa 12.11.2026 (E4-3: ”vaatii kertoat taustan”). | Lauseita, joissa on tällaisia kaksitulkintaisia infinitiivejä. |

### Kuuntelukoe E2, E3 ja E6

Toteutus:

- **E2:** `rajageminaatio.py`:n uusi laukaisijatyyppi `connegative`. Kieltomuoto tunnistetaan siitä, että Voikon mukaan sana voi olla yksikön 2. persoonan imperatiivi ja sitä edeltää heti kieltoverbi indikatiivissa (ei, en, et, emme, ette, eivät). **Käytössä 12.11.2026 alkaen** (`ENABLED`).
- **E3:** `rajageminaatio.py`:n asetus `VOWEL_H` (tai `mark(..., vowel_h=True)`): vokaalilla alkavan sanan edellä laukaisevan sanan loppuun tulee h. Koskee kaikkia käytössä olevia laukaisijoita. **Pois päältä.**
- **E6:** `f5fi.lower_first` ja asetus `f5fi.LOWER_FIRST` (tai `normalize_text(..., lower=True)`): jokaisen virkkeen ensimmäinen kirjain pieneksi. Iso alkukirjain jää sanoihin, jotka Voikko tuntee vain niminä (”Leena”, ”Helsinki”, ”Eino”), ja sanoihin, joissa on muitakin isoja kirjaimia (”EU”). ”Tuuli” ja ”Aamulla” muuttuvat pieniksi, koska ne ovat myös tavallisia sanoja. **Käytössä 12.11.2026 alkaen.**
- Yksikkötestit: `tests/test_text.py` (`ConnegativeTest`, `VowelHTest`, `test_lower_first`).

Koeasetelma: 21 uutta lausetta, jotka eivät ole Koulutusmateriaalit-vertailuaineistossa (E2 6, E3 7 ja E6 8). Jokaisesta lauseesta tehtiin versio A (ilman testattavaa sääntöä) ja B (sääntö päällä) samalla siemenellä 1. Kuuntelusivulla versiot ovat sokkona arvotussa järjestyksessä, ja arvonnan avain on tiedostossa `koe.json`. E3:ssa molemmissa versioissa on E2 päällä, jotta vain h-merkintä vaihtelee. E6:sta tehtiin lisäksi siemenet 2 ja 3 Whisper-tarkistukseen (kansio `whisper-e6/`). Lauseet ja mallille menneet tekstit ovat tiedostossa `koe.json`, ja kokeen voi toistaa skriptillä `tee.py`.

Whisperin tulos (11.11.2026, ennen kuuntelua):

- **E6:** isolla alkukirjaimella Whisper kuuli ensimmäisen sanan oikein 18 otossa 24:stä (”Kutkijat” 2, ”Viittää” 3 ja ”Esiakas” 1), pienellä alkukirjaimella 24 otossa 24:stä. Siemenet 1–3, kahdeksan lausetta.
- **E3:** h-versiossa Whisper kuuli kolmessa lauseessa seitsemästä h:n seuraavan sanan alussa (”harvioimaan”, ”hikkunan”, ”huida”). Merkintä voi siis kuulua oikeana h:na eikä kurkkusulkeumana. Kuuntelu ratkaisee.
- **E2:** Whisper kuuli molemmat versiot samoin kaikissa kuudessa lauseessa, joten se ei erota kahdennusta.
- Lauseen E3-7 molemmissa versioissa Whisper kuuli ”Annattaa” (”Kannattaa”). Se on E6:n ilmiö, sillä E3-koe tehtiin isolla alkukirjaimella.

Juuson kuuntelu (12.11.2026, sokkona; B = sääntö päällä):

| Koe | B parempi | A parempi | Ei eroa | Juuson huomiot |
|---|---|---|---|---|
| E2 kieltomuoto | 3 (”ei voim myöhästyä”, ”emme ehdik käydä”, ”et tarvitsem mitään”) | 1 (”ei kannatat tehdä”) | 2 (”en olen nähnyt”, ”ei kannatat tallentaa”) | – |
| E3 h vokaalin edellä | 1 (”opetellah uuden”) | 3 (”pystyh arvioimaan”, ”avatah ikkunan”, ”saah uida”) | 3 | ”hikkunan” ja ”huida”: h kuuluu hyvin selvästi |
| E6 pieni alkukirjain | 4 (”tutkijat”, ”riittää”, ”asiakas”, ”kolmas”) | 1 (”tulos”) | 2 | Isolla: ”hutkijat”, ”äsiakas”. E3-7:n molemmissa versioissa alun k ei kuulu (”Kannattaa” isolla). Yksi pari jäi arvioimatta. |

Päätelmät:

- **E6** toimii: kuuntelu 4–1 ja Whisper 24/24 vs. 18/24. Koulutusmateriaaleissa sama korjaus hyväksyttiin kahdessa lauseessa.
- **E2** on enimmäkseen parannus (3–1, kaksi tasan). Koulutusmateriaaleissa ”kannatas” hyväksyttiin kahdesti ja ”ei olet tehdä” jäi valitsematta. Yhteensä 5 parempaa, 2 huonompaa tai valitsematta jäänyttä ja 2 tasan. Kumpikin heikompi tapaus on t:n kahdennus (”kannatat tehdä”, ”olet tehdä”), mutta aineisto on liian pieni sääntöön.
- **E3** ei toimi yleissääntönä: h kuuluu usein oikeana h:na. Se jää pois päältä. Käsin kirjoitettu h on yhä keino silloin, kun kuulija huomaa sanojen liimautuvan yhteen (Koulutusmateriaaleissa neljä hyväksyttyä lausetta).

### Kuuntelukoe E1, E4, E5, E7 ja E8

Toteutus (kokeen aikana pois päältä, 12.11.2026 alkaen oletuksena päällä):

- **E1:** `f5fi.COLON_SPLIT` (tai `synthesize(..., colon_split=True)`) ja `f5fi.split_colon`. Teksti jaetaan kohdasta, jossa kaksoispisteen jälkeen tulee välilyönti, joten kellonaika ”10:30” säilyy. Ensimmäinen osa päättyy pisteeseen, myöhemmät osat alkavat pienellä kirjaimella, ja osat liitetään `COLON_GAP_S` = 0,3 s hiljaisuudella. Osien välistä hiljaisuutta ei jätetä ylimääräiseksi.
- **E4:** `rajageminaatio.LIST_GOVERNOR` (tai `mark(..., list_governor=True)`). -aa/-ää-loppuinen infinitiivi pilkun tai ja-, tai- tai sekä-sanan jälkeen tulkitaan infinitiiviksi, kun samassa virkkeessä on aiemmin hallitsevan verbin infinitiivi.
- **E5:** laukaisijatyyppi `imperative` on ollut moduulissa jo ennestään, joten koe tehtiin lisäämällä se joukkoon `ENABLED`. Mukana on myös 6.11. hylätty lause ”Älä mene sinne, vaan tule tänne”.
- **E7:** `rajageminaatio.mark_compounds(..., e_gemination=True)` tai `COMPOUND_E`. Yhdyssanan osat saadaan Voikon `STRUCTURE`-kentästä. Kahdennus tehdään vain, kun alkuosa on perhe- tai huone-tyyppinen e-sana. Sen tunnistaa siitä, että Voikko hyväksyy partitiivin -tta/-ttä (perhettä, saatetta). Näin ”nukketeatteri” ja ”itsepalvelu” jäävät ennalleen.
- **E8:** `mark_compounds(..., vowel_hyphen=True)` tai `COMPOUND_HYPHEN`. Tavuviiva lisätään yhdyssanan osien rajalle, kun vokaali kohtaa vokaalin. Sääntö koskee kaikkia osarajoja, joten ”tekoälyosaaminen” saa muodon ”teko-äly-osaaminen”.
- Yksikkötestit: `tests/test_text.py` (`ListAndCompoundTest`, `ColonSplitTest`, `test_imperative_is_on_by_default`).

Koeasetelma on sama kuin edellisessä kokeessa: 26 lausetta (E1 5, E4 5, E5 6, E7 5 ja E8 5), versiot A ja B siemenellä 1, sokkona ja arvotussa järjestyksessä (`koe.json`, `tee.py`). Molemmissa versioissa ovat mukana jo käytössä olevat E2 ja E6.

Whisperin tulos (12.11.2026, ennen kuuntelua):

- **E8:** ilman tavuviivaa Whisper kuuli yhdyssanan väärin neljässä lauseessa viidestä (”kahvilaurittaja”, ”tekoa lyö saaminen”, ”pitopalveluudittaja”, ”ruokauhja”). Tavuviivan kanssa vain yksi meni väärin (”ruokaohja”). Ilmiö on siis yleinen eikä koske vain sanaa ”pitopalveluyrittäjä”.
- **E1:** jaetussa versiossa Whisper kirjoitti kaksoispisteen kohdalle pilkun tai pisteen kaikissa viidessä lauseessa, yhtenäisessä versiossa ei yhdessäkään (yhtä pilkkua lukuun ottamatta). Tauko siis kuuluu. Sävelkulku ratkeaa kuuntelemalla.
- **E7:** Whisper kuuli ”venemmatka” muodossa ”venen matka”. Muut olivat samat.
- **E4 ja E5:** Whisper ei erota versioita.

Juuson kuuntelu (12.11.2026, sokkona; B = sääntö päällä):

| Koe | B parempi | A parempi | Ei eroa | Juuson huomiot |
|---|---|---|---|---|
| E1 kaksoispiste | 5 | 0 | 0 | ”Kaksoispiste toimii hyvin”. Lisäksi ”sammuta laite” vaatii kahdennuksen ”sammutal laite” (E5). |
| E4 luettelo | 2 (”kääntääs sen”, ”vaihtaar renkaat … täyttääl lomakkeen”) | 1 (”… ja kirjoittaar raportti”) | 2 | ”kertoa taustan” vaatii ”kertoat taustan” (E14). ”ehdottaa otsikoita” vaatii kurkkusulkeuman. |
| E5 käskymuoto | 5 | 0 | 1 (”Älä mene sinne, vaan tule tänne”) | ”kiinni kaiteesta” → ”kiinnik kaiteesta” (E13). |
| E7 yhdyssanan kahdennus | 4 (”saatekkirjeen … kirjekkuoreen”, ”perhettuttumme”, ”vaatekkaappi”, ”venemmatka”) | 0 | 1 (”huonekkalut”) | – |
| E8 tavuviiva vokaalirajalle | 3 (”kahvila-yrittäjä”, ”teko-äly-osaaminen”, ”pitopalvelu-yrittäjä”) | 0 | 1 (”talo-yhtiö”) | E8-5 jäi arvioimatta: ”…ohjel löytyi” (E12). |

Päätelmät:

- **E1, E5, E7 ja E8** paransivat lauseita, eikä yksikään lause huonontunut. E5:n 6.11. hylätty lause ”Älä mene sinne, vaan tule tänne” kuulosti nyt yhtä hyvältä merkittynä.
- **E4** on samaa tasoa kuin käyttöön otettu E2 (2–1, kaksi tasan). Ainoa huonompi tapaus oli ja-sanan jälkeinen ”kirjoittaar raportti”. Juuson huomiot (E14 ja kurkkusulkeuma) osoittavat, että luetteloissa kahdennusta tarvitaan pikemmin enemmän kuin vähemmän.
- Kokeesta syntyi kolme uutta ehdotusta: E12, E13 ja E14.
- **Päätös 12.11.2026:** Juuso otti käyttöön kaikki viisi.

E2:n myötä myös sivuhavainto kohdasta 2 korjaantui: moduuli merkitsee nyt molemmat kohdat (”ei kannatas syöttääp palveluun”), kun tekstiä ei merkitä käsin.

### Koeajo E9 ja E10

Siemenvalintatila (E9) ja taukojen enimmäispituus (E10) kokeiltiin 12.11.2026 kahdella sarjan 5 tyyppisellä lauseella (kansio `data/vertailu/2026-11-12_siemenvalinta/`, sivu `index.html`, tiedot `siemenet.json`). Malli oli perusmalli, viite `viite_selitys_2`.

| Lause | Otot | Juuson valinta |
|---|---|---|
| lause01 ”Ilmiöstä käytetään nimeä metakognitiivinen laiskuus.” | siemenet 4–6 | siemen 4 |
| lause02 ”Juna oli puoli tuntia myöhässä. Siksi ehdin lukea koko lehden.” | siemenet 4–5 | siemen 4 |
| lause02-tauot015, sama lause, `--max-pause 0.15` | siemenet 4–5 | siemen 4 |

- Juuso valitsi kaikista lauseista siemenen 4. Myös kohdan 8 kierroksella 7 siemen 4 valittiin kolmessa niistä neljästä lauseesta, joihin kelvollinen otto löytyi. Siemen 4 ei silti ole yleisesti paras, koska sama siemen antaa eri tekstillä eri prosodian.
- Konnektiivi ”Siksi” tuli molemmissa lause02:n versioissa melko voimakkaasti. Juuson arvion mukaan se tasoittunee hienosäädössä.
- Taukoraja lyhensi lause02:ssa virkkeiden välisen tauon 0,33 sekunnista 0,15 sekuntiin, koska lauseen ainoa tauko oli pisteen kohdalla. Juuso hyväksyi myös lyhennetyn version.

## Vertailuaineisto hienosäädetyn mallin arviointiin

Kansio: `data/vertailu/2026-11-11_koulutusmateriaalit/` (32 Mt, 141 ottoa; `data/` ei kuulu versionhallintaan). Tiedostot on kopioitu Koulutusmateriaalit-projektista, joten ne säilyvät, vaikka alkuperäiset siirrettäisiin.

- `index.html`: paikallinen kuuntelusivu, jossa otot on ryhmitelty ilmiöittäin. Avaa komennolla `open data/vertailu/2026-11-11_koulutusmateriaalit/index.html`. Älä julkaise sivua tai ääntä verkkoon.
- `kuvaus.json`: jokaisesta otosta alkuperäinen lauseteksti, mallille annettu teksti ennen ja jälkeen moduulin käsittelyn (`kirjoitettu_mallille`, `mallille_meni`), siemen, Whisperin litterointi, kierros, Juuson päätös ja lähdetiedosto.
- Kansiot `01-kaksoispiste` … `08-prosodia` vastaavat tämän dokumentin kohtia. Tiedostonimi on muotoa `<lause>__<päätös>__<versio>.wav`, esimerkiksi `V1-05-s2__hyvaksytty__tarvitseh.wav`.
- Päätökset: **hyväksytty** (Juuso valitsi), **hylätty** (Juuso hylkäsi nimenomaan tämän) ja **ei valittu** (kuunneltiin, mutta valittiin toinen; ei välttämättä virheellinen).
- `kokoa.py` kokosi kansion. Sen voi ajaa uudelleen f5-fi:n juuresta, jos lähdetiedostot ovat yhä paikallaan.
- Raa'at otot ovat 24 kHz:n mono-WAV-tiedostoja. Versiot, joissa tauot on muokattu tai osat liitetty, ovat kuuntelusivun 48 kHz:n tiedostoja (`jalkikasitelty: true`).

**Käyttö hienosäädön jälkeen.** Tuota hienosäädetyllä mallilla jokaisen lauseen alkuperäinen teksti (kentässä `teksti`, ilman käsin tehtyjä korjauksia) samalla viitteellä ja samoilla siemenillä. Vertaa tulosta kuuntelemalla hyväksyttyyn ja hylättyyn ottoon. Hienosäätö on onnistunut ilmiön kohdalla, jos malli tuottaa hyväksytyn kaltaisen version ilman tekstikorjausta. Prosodialauseissa (kohta 8) kannattaa tuottaa useita siemeniä ja verrata, kuinka moni niistä kelpaa: perusmallilla kelpasi yksi kahdeksasta tai yhdeksästä.
