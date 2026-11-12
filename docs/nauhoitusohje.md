# Nauhoitusohje: oma ääni F5-TTS:ää varten

Ohjeessa on kaksi vaihetta:

- **Vaihe A** on lyhyt kokeilu, jossa nauhoitat kolme viitenäytettä ja kuulet, kuinka hyvin F5 matkii ääntäsi ilman hienosäätöä. Nauhoitukseen kuluu noin 15 minuuttia.
- **Vaihe B** on hienosäätöä varten nauhoitettava aineisto. Tavoite on noin tunti puhetta, ja vähimmäismäärä on noin 30 minuuttia. Aineiston voi nauhoittaa useassa osassa eri päivinä.

Vaihe A2 tarkentaa vaihetta A: siinä nauhoitetaan eläytyviä viitteitä pitkiä lukutekstejä varten.

Tee vaihe A ensin. Sen tuloksen perusteella päätämme, kuinka paljon aineistoa vaiheessa B kannattaa nauhoittaa.

## 1. Paikka ja välineet

- **Hiljainen ja pehmeä huone.** Verhot, matto ja huonekalut vaimentavat kaikua. Tyhjä huone ja kylpyhuone kaikuvat liikaa.
- **Ei taustaääniä.** Sammuta tuuletin ja ilmanvaihto, jos se on mahdollista, ja laita ilmoitukset pois päältä.
- **Mikrofoni.** Käytä samaa mikrofonia kuin viitenäytteiden toisella kierroksella (`data/viite/v2-wav`). Sillä tulos oli selvästi parempi kuin ensimmäisellä mikrofonilla. **Käytä kaikissa nauhoituksissa samaa mikrofonia ja samaa huonetta.** Hienosäätö oppii myös mikrofonin ja huoneen äänen, joten vaihtelu heikentää tulosta.
- **Etäisyys.** Pidä etäisyys mikrofoniin samana, noin 15–20 cm. Lyhyt etäisyys tuo ääneen täyteyttä ja vähentää huoneen kaikua ja kohinaa. Käytä pop-suodatinta tai pidä mikrofoni hieman suun sivussa, jotta p- ja t-äänteet eivät pamahda.
- **Nauhoitusohjelma ja tiedostomuoto.** Käytä samaa ohjelmaa ja samoja asetuksia kuin v2-näytteissä. WAV-muoto sopii hyvin, eikä näytteenottotaajuudella (44,1 tai 48 kHz) ole väliä.
- **Ei jälkikäsittelyä.** Jätä pois kohinanpoisto, äänen parannus, taajuuskorjaus ja kompressori, koska F5 kopioisi niiden sivuvaikutukset. Normalisointiakaan ei tarvitse tehdä itse, koska valmisteluskripti tasaa kaikkien äänitteiden voimakkuuden samalle tasolle. Varo vain, ettei ääni leikkaudu: huippujen pitää jäädä selvästi alle maksimitason. Skripti varoittaa, jos äänite on leikkautunut.
- **Taustakohina.** V2-näytteissä kohina oli selvästi suurempaa kuin ensimmäisissä näytteissä (−48…−58 dB). Ennen pitkää nauhoitusta kannattaa tehdä koenauhoitus ja kuunnella hiljaiset kohdat kuulokkeilla. Jos kuulet suhinaa, pienennä mikrofonin vahvistusta ja siirry lähemmäs mikrofonia.
- **Ääni.** Nauhoita silloin, kun ääni on tavallinen. Älä nauhoita flunssassa tai käheänä. Pidä vesilasi lähellä.

Tee ensin 10 sekunnin koenauhoitus ja kuuntele se kuulokkeilla. Jos kuulet kaikua, huminaa tai säröä, vaihda paikkaa tai siirrä mikrofonia ennen varsinaista nauhoitusta.

## 2. Vaihe A: viitenäytteet

Nauhoita jokaisesta tekstistä 2–3 ottoa. Jätä alkuun ja loppuun noin sekunnin hiljaisuus.

**viite_neutraali** (rauhallinen, selkeä kirjakieli)
> Tervetuloa. Kerron tänään lyhyesti, miten uusi järjestelmä toimii ja mitä siitä kannattaa tietää.

**viite_puhekieli** (rento, kuin puhuisit kollegalle)
> No moi! Mä ajattelin, et käytäis tää juttu nopeesti läpi, niin päästään sit eteenpäin.

**viite_kerronta** (rauhallinen lukuääni, kuin lukisit kirjaa ääneen)
> Ilta oli jo pimennyt, kun saavuimme mökille. Järvi oli tyyni, ja rannasta kuului kaukainen kuikan huuto.

Nimeä tiedostot tekstin ja oton mukaan: `viite_neutraali_1.wav`, `viite_neutraali_2.wav`, `viite_puhekieli_1.wav` ja niin edelleen.

F5 kopioi viitenäytteestä äänen lisäksi tempon ja sävyn. Siksi kolme erilaista näytettä kertoo, millaisia ääniä mallilla saa aikaan.

## 2b. Vaihe A2: eläytyvät viitenäytteet

Ensimmäisten näytteiden kuuntelussa kävi ilmi kaksi asiaa. Rauhallinen kerrontaviite tuotti kielellisesti hyvää mutta melko tasaista luentaa. Puhekieliviite toi luentaan vauhtia, mutta pitkässä tekstissä se kuulosti kiireiseltä, ja ääneen tuli säröä. Tässä vaiheessa nauhoitetaan viitteitä, joissa on eläytymistä mutta ei kiirettä.

Viitteen tyyli on tällä hetkellä tärkein keino vaikuttaa luennan eloisuuteen. Se pysyy tärkeänä myös hienosäädön jälkeen, sillä hienosäädetty malli kopioi edelleen viitteen sävyn ja tempon.

### Millainen on hyvä viite

- **Pituus on 8–10 sekuntia.** F5 lyhentää yli 12 sekunnin viitteen, joten pidempi viite ei auta. Lyhyestä viitteestä malli saa liian vähän tietoa äänestäsi.
- **Viitteen tyyli vastaa sitä, mitä haluat mallin tuottavan.** Malli lukee koko pitkän tekstin viitteen tyylillä, joten viite kannattaa nauhoittaa eläytyvän kertojan äänellä eikä rauhoittavalla lukuäänellä.
- **Viitteessä on vaihtelua.** Sama näyte voi sisältää kerrontaa ja yhden vuorosanan, jolloin mallilla on esimerkki sekä kertojasta että henkilöstä.
- **Voimakkuus pysyy tasaisena.** Yksittäinen kova kohta, kuten innokas huudahdus tai pamahtava p-äänne, estää nostamasta muuta näytettä oikealle tasolle. Puhekieliviitteessä "No moi!" teki juuri näin, ja koko näyte jäi hiljaiseksi. Eläydy sävyllä ja tempolla, älä äänen voimakkuudella. Jos jokin kohta on luontaisesti kova, siirry hieman kauemmas mikrofonista.
- **Tempo on luonteva.** Kiireinen viite tuottaa kiireistä ja helposti särisevää puhetta. Pidä virkkeiden välissä tauot, äläkä nopeuta lukemista eläytymisen vuoksi.
- **Viite päättyy kokonaiseen virkkeeseen,** ja sen jälkeen on sekunnin hiljaisuus.
- **Nauhoitusasetukset pysyvät samoina.** Aiemmat kerronta- ja puhekieliviitteet on nauhoitettu eri taajuuksilla (44,1 ja 48 kHz), mikä viittaa siihen, että asetukset ovat vaihdelleet. Tarkista ennen nauhoitusta, että ohjelma, mikrofoni, vahvistus ja tiedostomuoto ovat samat kuin aineiston nauhoituksessa.

### Miten eläytyä

- **Kerro, älä lue.** Kuvittele kertovasi tapahtumaa ystävälle, joka kuuntelee mielellään. Lukuääni muuttuu helposti tasaiseksi ja ennalta arvattavaksi.
- **Nosta tärkein sana esiin.** Jokaisessa virkkeessä on yleensä yksi sana, jonka varassa merkitys on. Painota sitä hieman ja hidasta ennen sitä.
- **Pidä tauko ennen yllätystä.** Lyhyt tauko ennen käännettä tai vuorosanaa luo odotusta.
- **Anna henkilölle oma äänensä.** Vuorosanaa ei tarvitse näytellä. Riittää, että sävy, tempo tai korkeus muuttuu vähän, kun puhuja vaihtuu kertojasta henkilöksi.
- **Anna tunnelman näkyä äänessä.** Hymy kuuluu äänessä. Haikeassa kohdassa voit hiljentää ja hidastaa. Jännittävässä kohdassa voit pidättää ja kiihdyttää.

### Viitetekstit

Jokainen teksti on noin 17–21 sanaa, eli luettuna noin 8–10 sekuntia. Tekstit 1, 2 ja 6 on otettu kertomuksesta *Uusi naapuri* sen myöhemmistä kohdista. Lähtötasonäyte on luettu kertomuksen alusta, joten nämä kohdat eivät mene sen kanssa päällekkäin. Tekstit 4 ja 5 ovat muista lukuteksteistä, ja teksti 3 on kirjoitettu tätä varten.

**viite_rengas** (lämmin huumori, kerronta ja vuorosana)
> Rengasrauta kimposi pensaaseen. Eino haki sen ja antoi takaisin. – Tollanen pieni reikä, hän sanoi, – ja koko pyörä seisoo kolme vuotta.

**viite_lumi** (haikea ja hiljainen, lopussa lohdullinen käänne)
> Marraskuun lopussa satoi ensimmäinen lumi. – Nyt alkaa se pitkä talvi, sanoin. – Ei se niin pitkä oo, Eino sanoi. – Kun on luettavaa.

**viite_jannite** (jännite, joka kasvaa loppua kohti)
> Ovi narahti. Pysähdyin kuuntelemaan, mutta talossa oli aivan hiljaista. Sitten keittiöstä kuului kolahdus, ja joku kuiskasi nimeni.

**viite_juhla** (lämmin innostus, puhe yleisölle)
> Kiitos koko koulun puolesta! Ja nyt pyydän kaikkia nousemaan seisomaan. Annetaan Pentille aplodit, jotka kuuluvat kellariin asti!

**viite_selitys** (innostunut asiantuntija, joka kertoo kiinnostavasta asiasta)
> Moni on huomannut, että vaikea asia selkenee yön aikana. Ja tälle on olemassa selitys: aivot tekevät nukkuessa töitä.

**viite_kirjat** (vuoropuhelu kahden henkilön välillä, arkinen puhekieli)
> Viikon päästä hän koputti oveeni. – Onks sillä kirjailijalla muita? – On. Ainakin viisi. – Hyvä, hän sanoi. – Tuo ne kaikki.

Lue jokainen teksti kolmella tavalla ja nimeä otot numeroilla:

1. **hillitysti**, kuten luet tavallisesti, mutta ajatuksella (`viite_rengas_1.wav`)
2. **eläytyen**, niin kuin haluaisit mallin lukevan (`viite_rengas_2.wav`)
3. **vähän liioitellen**, kuin lukisit lapselle iltasatua (`viite_rengas_3.wav`)

Liioiteltu otto voi kuulostaa nauhoittaessa hölmöltä, mutta malli tasoittaa sävyä. Siksi liioiteltu viite tuottaa usein luontevimman tuloksen.

Tallenna otot kansioon `data/raw/viitenäytteet-v3/`, niin ne pysyvät erillään aiemmista. Kaikkia tekstejä ei tarvitse nauhoittaa. Jo kaksi tai kolme tekstiä kolmella tavalla kertoo, mikä tyyli toimii. Kaikkiaan nauhoitukseen kuluu noin 15 minuuttia.

Kun otot ovat valmiit, Claude käsittelee ne samaan tapaan kuin aiemmat viitteet. Sitten Claude tuottaa jokaisella otolla saman testikatkelman, jota käytettiin lähtötasonäytteessä, ja kokoaa ne kuuntelusivulle. Paras otto kertoo samalla, miten pitkät lukutekstit (vaihe B2) kannattaa lukea.

## 3. Vaihe B: hienosäätöaineisto

Aineistossa on kolmenlaista puhetta. Vaihtelu auttaa mallia oppimaan äänesi monenlaisissa lauseissa.

| Osa | Puhetta | Mitä nauhoitetaan |
|---|---|---|
| B1. Lauseet | noin 10 min (nauhoitus taukoineen noin 20 min) | 150 valmista lausetta tiedostosta `lukulauseet.md` |
| B2. Pitkä lukeminen | 30–45 min | Valitsemaasi tekstiä luettuna |
| B3. Vapaa puhe | 10–20 min | Puhetta aiheista ilman käsikirjoitusta |

Mieti ennen nauhoitusta, kumpaa tyyliä tarvitset projekteissasi enemmän: kirjakieltä vai puhekieltä. Painota aineistoa sen mukaan. Malli puhuu myöhemmin parhaiten sellaista kieltä, jota aineistossa on eniten.

### B1. Lauseet

Lauseet ovat tiedostossa [lukulauseet.md](lukulauseet.md) viitenä 30 lauseen sarjana. Ne kattavat suomen äänteet monipuolisesti: pitkät vokaalit ja kaksoiskonsonantit, diftongit, ng- ja nk-yhtymät, kysymykset, huudahdukset ja pitkät virkkeet. Sarja 4 on puhekieltä. Sarja 5 lisättiin 11.11.2026: se harjoittaa lausepainoa, luetteloita ja rajakohtia, joissa perusmalli epäonnistui ([ääntämishavainnot](aantamishavainnot.md)). Sarjan 5 alussa on omat lukuohjeet.

- **Nauhoita yksi sarja yhteen tiedostoon:** `lauseet_1.wav` … `lauseet_5.wav`.
- **Pidä lauseiden välissä noin kahden sekunnin tauko.** Tauon kohdalta äänite pilkotaan lauseiksi. Älä sano lauseen numeroa ääneen.
- **Jos lause menee pieleen,** pidä tauko ja lue koko lause uudelleen. Pilkkominen löytää uusinnan, ja huonompi otto poistetaan.
- **Lue lauseet luontevasti,** älä tavaten. Kysymys saa kuulostaa kysymykseltä ja huudahdus huudahdukselta.

### B2. Pitkä lukeminen

**Valmiit lukutekstit:** Kansiossa `data/raw/aineisto/` on viisi nykysuomenkielistä tekstiä, jotka on kirjoitettu tätä aineistoa varten. Tekstilajit ovat erilaisia, jotta aineistoon tulee monenlaista sävelkulkua:

| Tiedosto | Teksti | Sanoja | Lukuaika |
|---|---|---|---|
| `lukeminen_1.txt` | Kertomus *Uusi naapuri*, jossa on puhekielistä vuoropuhelua | 1 196 | noin 10 min |
| `lukeminen_2.txt` | Asiateksti *Miksi ihminen nukkuu* | 926 | noin 8 min |
| `lukeminen_3.txt` | Ohje *Näin leivot ruisleivän juuresta* | 967 | noin 8 min |
| `lukeminen_4.txt` | Juhlapuhe *Puhe Pentin eläkejuhlassa* | 791 | noin 7 min |
| `lukeminen_5.txt` | Selittävä teksti *Miten uusi taito opitaan* (lisätty 11.11.2026): konnektiivit, uudet termit, luettelot ja kaksoispisteet. Lue niin kuin selittäisit asiaa kuulijalle, ja paina uusia termejä. | 323 | noin 3 min |

Yhteensä tekstejä on noin 36 minuuttia. Luvut on kirjoitettu sanoina. Lue myös väliotsikot ääneen ja pidä niiden jälkeen lyhyt tauko. Lue vuorosanat niin kuin henkilö ne sanoisi, ja juhlapuhe niin kuin pitäisit sen yleisölle.

Aiemmin lukutekstinä oli Juhani Ahon *Rautatie* (1884), mutta sen vanha kieli teki lukemisesta takkuista. Ahon tekstit ovat tallessa kansiossa `data/raw/lahdetekstit/gutenberg-10481/`.

Voit käyttää myös omia tekstejäsi, kuten artikkeleita tai luentomateriaaleja. Tallenna silloin teksti samaan kansioon samannimiseen .txt-tiedostoon.

Ohjeita lukemiseen:

- **Nauhoita yksi osa yhteen tiedostoon:** `lukeminen_1.wav` luetaan tiedostosta `lukeminen_1.txt` ja niin edelleen. Koko osaa ei tarvitse lukea kerralla. Jos lopetat kesken, jatka myöhemmin uuteen tiedostoon (`lukeminen_1b.wav`) siitä virkkeestä, johon jäit. Kohdistus löytää luetut virkkeet itse.
- **Teksti tarkistetaan lukutiedostosta.** Sen avulla varmistetaan, että Whisperin litterointi vastaa sitä, mitä sanoit.
- **Lue niin eläytyen kuin haluaisit mallin lukevan.** Malli oppii lukutapansi pitkistä äänitteistä: tasaisesta luennasta tasaisen lukutavan ja eläytyvästä luennasta eläytyvän. Käytä samaa tyyliä, joka toimi parhaiten viitekokeessa (vaihe A2). Pidä tempo luontevana ja virkkeiden välissä tauko.
- **Kirjoitusvirheet ja takeltelut eivät haittaa.** Jos takeltelet, pidä tauko ja lue koko virke uudelleen alusta. Kohdistus ottaa käyttöön viimeisen oton. Jos korjaat vain sanan virkkeen keskellä, virke merkitään tarkistettavaksi.
- **Pidä virkkeiden välissä lyhyt tauko,** vaikka vain hengenvedon verran. Leikkeet leikataan virkkeiden välisistä tauoista. Jos virkkeet menevät yhteen ilman taukoa, raja merkitään tarkistettavaksi.

### B3. Vapaa puhe

Vapaa puhe opettaa mallille luontevaa rytmiä, joka luetusta tekstistä usein puuttuu. Valitse aihe ja puhu siitä 2–4 minuuttia kuin kertoisit asiasta kollegalle. Aiheita voivat olla esimerkiksi nämä:

- mitä teit viime viikonloppuna
- työpäiväsi kulku
- jokin projekti, jonka parissa työskentelet nyt
- muisto lapsuudesta tai koulusta
- matka, joka on jäänyt mieleen
- kirja, elokuva tai sarja, josta pidit
- miten neuvoisit uutta työntekijää aloittamaan
- mitä mieltä olet etätyöstä

Nimeä tiedostot `vapaa_1.wav`, `vapaa_2.wav` ja niin edelleen. Täytesanat ja tauot kuuluvat luontevaan puheeseen, mutta pidä pitkät miettimistauot alle viiden sekunnin.

## 4. Tiedostojen tallennus

Tallenna vaiheen B tiedostot kansioon `Kielimallit/f5-fi/data/raw/aineisto/`, niin ne pysyvät erillään viitenäytteistä. Kansio ei kuulu versionhallintaan, eivätkä tiedostot lähde koneelta. Voit myös tallentaa ne vaikkapa työpöydälle ja kertoa Claudelle, missä ne ovat.

## 5. Kun äänitteet ovat valmiit

Claude tekee seuraavat vaiheet:

1. Muuntaa äänitteet 24 kHz:n mono-WAV-muotoon macOS:n omalla `afconvert`-työkalulla ja normalisoi niiden voimakkuuden samalle tasolle.
2. Pilkkoo lauseiden sarjat taukojen kohdalta ja pitkät luennat virke kerrallaan. Pitkässä luennassa virkkeet etsitään kohdistamalla Whisperin litterointi lukutekstiin.
3. Litteroi pätkät paikallisella Whisperillä ja vertaa litterointia luettuun tekstiin. Puhekielisissä lauseissa Whisper muuttaa usein sanat kirjakielisiksi, joten ne korjataan vastaamaan sitä, mitä sanoit.
4. Kokoaa sinulle tarkistettavaksi listan pätkistä, joissa litterointi ja teksti poikkeavat toisistaan. Kuuntelet ne ja päätät, korjataanko vai poistetaanko pätkä.
5. Ajaa tarkistettuihin litterointeihin saman esikäsittelyn, jota käytetään synteesissä (rajageminaatio ja pienet Ä ja Ö). Näin malli oppii yhdistämään merkityn tekstin äänitteisiisi, joissa kahdentuma kuuluu luonnostaan.
6. Tekee aineistosta F5-TTS:n harjoitusdatan ja ajaa koneella lyhyen kokeilun, joka varmistaa, että hienosäätö käynnistyy.
7. Varsinainen hienosäätö ajetaan näytönohjaimella, esimerkiksi yliopiston GPU-palvelimella. Tästä sovitaan erikseen.

## 6. Hienosäädetyn mallin säilytys

Hienosäädetty malli tuottaa äänelläsi mitä tahansa tekstiä. Säilytä se omalla koneellasi tai yliopiston palvelimella, äläkä jaa mallia tai `checkpoints/`-kansiota julkisesti.
