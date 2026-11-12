# CSC:n Roihu hienosäädön laskenta-alustana

Selvitetty 2026-11-09 CSC:n dokumentaatiosta. Lähteet ovat lopussa.

## Yhteenveto

Roihu sopii hyvin F5:n hienosäätöön ja VoxCPM2:n ajamiseen. Yksi Roihun GPU riittää tämän kokoiseen työhön moninkertaisesti, ja käyttö on maksutonta suomalaisen korkeakoulun tutkimus- ja opetuskäytössä. Ennen käyttöä on ratkaistava kolme asiaa:

1. **Käyttöoikeus.** Tarvitset CSC-käyttäjätunnuksen, CSC-projektin, Roihu-palvelun projektiin ja projektille GPU-laskutusyksiköitä. Nämä haetaan MyCSC-portaalissa.
2. **ARM-arkkitehtuuri.** Roihun GPU-solmujen suorittimet ovat ARM-suorittimia. PyTorch on valmiina moduulina, mutta F5:n muiden riippuvuuksien toimivuus on testattava ensin lyhyellä testiajolla.
3. **Aineiston luonne.** Ääninäytteet ovat henkilötietoa. Roihun arkaluontoisen datan ympäristö ei ole vielä käytössä. Päätä itse ja tarvittaessa yliopiston kanssa, sopiiko oman äänesi aineiston käsittely Roihun tavallisella puolella.

Puhti ja Mahti eivät enää ole vaihtoehtoja. Niiden laskenta on lopetettu kesällä 2026, ja Roihu korvaa ne. Aiempi maininta Puhtista ja Mahtista ei siis enää pidä paikkaansa.

## Roihun GPU-solmut

| | |
|---|---|
| GPU:t | 4 × Nvidia GH200 Grace Hopper solmua kohden, eli H100-GPU ja ARM-suoritin samassa piirissä |
| GPU-muisti | 96 Gt HBM3 GPU:ta kohden, lisäksi noin 117 Gt keskusmuistia GPU:ta kohden |
| Suorittimet | ARM, 72 ydintä GPU:ta kohden. Roihun CPU-puoli on x86, ja sille rakennetut ohjelmat eivät toimi GPU-puolella. |
| Kirjautuminen | `roihu-gpu.csc.fi` |
| Paikallinen levy | 150 Gt `$TMPDIR`-tilaa käyttäjää kohden GPU-solmuilla |
| Verkkokäyttöliittymä | Jupyter, VS Code, TensorBoard ja MLflow selaimessa. Interaktiivisen GPU-käytön rajat ovat tiukemmat. |

**Jonot (partitiot):**

| Jono | Enimmäisaika | Käyttö |
|---|---|---|
| `gputest` | 15 min | Ympäristön ja riippuvuuksien testaus |
| `gpuinteractive` | 12 h | Interaktiivinen työ, esimerkiksi Jupyter. GPU:n jakaminen pienempiin osiin ei ole vielä käytössä, joten jokainen istunto saa kokonaisen GPU:n. |
| `gpumedium` | 36 h | Varsinainen hienosäätö, 1–4 GPU:ta yhdellä solmulla |

## Ohjelmistot

- **PyTorch** on moduulina `python-pytorch` (2.13 oletuksena, myös 2.10), ja se toimii Roihun GPU-puolella. Moduulissa on CUDA ja cuDNN valmiina.
- Moduulit ovat Apptainer-kontteja, joiden päälle voi tehdä oman virtuaaliympäristön ja asentaa paketit `pip install` -komennolla. Jos tämä ei riitä, CSC:n konttia voi laajentaa tai rakentaa oman.
- **Riski:** Dokumentaatio ei kerro, onko kaikille pip-paketeille ARM-versiota. F5:n pääriippuvuuksille (transformers, vocos, librosa, soundfile) on yleensä olemassa ARM-paketit tai puhdas Python-versio. Varmuuden saa vain testaamalla `gputest`-jonossa. Paikallisen ympäristön `requirements-lock.txt` on tehty macOS:lle, joten sitä ei voi käyttää sellaisenaan.

## Kustannus

- Käyttö on maksutonta korkeakoulujen ja valtion tutkimuslaitosten akateemisessa tutkimuksessa, opetuksessa ja koulutuksessa. Käyttö kuluttaa silti projektin laskutusyksiköitä (BU), joita haetaan MyCSC:ssä yleensä 3–6 kuukauden arvioidulle tarpeelle.
- GPU-käytön hinta on 200 GPU-BU:ta GPU-tuntia kohden. CPU-ytimiä ja muistia ei laskuteta GPU-jonoissa erikseen.
- **Karkea arvio:** F5:n hienosäätö noin tunnin aineistolla vie arviolta muutamasta tunnista noin kymmeneen GPU-tuntiin. Se on noin 1 000–2 000 BU:ta, ja lisäksi kuluu testiajoja. Arvio ei perustu mittaukseen, ja se tarkentuu ensimmäisessä ajossa. Kun haet laskutusyksiköitä, varaa reilusti, esimerkiksi 10 000 GPU-BU:ta. Silloin laskentaan mahtuvat myös uusintakierrokset ja VoxCPM2-kokeet.

## Tietosuoja

- CSC kuvaa supertietokoneita "melko turvallisiksi oletuksena", mutta toteaa, ettei se voi taata, ettei tietomurto ole mahdollinen.
- Arkaluontoisen datan käsittely Roihussa on pilottivaiheessa syksyllä 2026. Yleinen käyttöönotto on arvioitu aikaisintaan alkuvuoteen 2027. Siinä työt eristetään verkosta ja Roihun jaetuilta levyiltä.
- Tavallisella puolella projektin kansiot näkyvät vain projektin jäsenille.
- Projektissa on aiemmin linjattu, että ääni ja aineisto pysyvät koneellasi tai yliopiston palvelimella. Roihu on yliopistojen yhteinen kansallinen palvelu, joten se sopii linjaukseen hengeltään. Päätös on kuitenkin sinun. Oman äänen nauhoitukset eivät yleensä kuulu erityisiin henkilötietoryhmiin, mutta äänimallia voi käyttää väärin. Siksi hienosäädetty malli kannattaa kopioida takaisin omalle koneelle ja poistaa Roihusta työn jälkeen. Tarkista tarvittaessa käytäntö yliopiston tietosuojavastaavalta.

## Käyttöönotto

1. Luo CSC-tunnus Haka-kirjautumisella osoitteessa my.csc.fi.
2. Luo tai liity CSC-projektiin. Projektin vastuuhenkilön on oltava korkeakoulun henkilökuntaa, ja projektin käyttötarkoitukseksi kirjataan tutkimus tai opetus.
3. Lisää projektiin Roihu-palvelu ja hae GPU-laskutusyksiköt.
4. Kirjaudu palvelimelle `roihu-gpu.csc.fi` ja kopioi tiedostot projektin scratch-kansioon: aineisto (`data/aineisto`, noin 20 Mt), perusmalli (`base/`, 1,3 Gt) ja skriptit.
5. Rakenna ympäristö moduulin `python-pytorch` päälle ja testaa F5:n tuottaminen ja lyhyt hienosäätö `gputest`-jonossa.
6. Aja varsinainen hienosäätö `gpumedium`-jonossa yhdellä GPU:lla, kopioi checkpointit takaisin kansioon `checkpoints/` ja vertaa tulosta lähtötasoon kuuntelemalla.

## Lähteet

- [Roihu: järjestelmän kuvaus](https://docs.csc.fi/computing/systems-roihu/)
- [Roihu: usein kysytyt kysymykset](https://docs.csc.fi/support/faq/roihu/)
- [Eräajojen partitiot](https://docs.csc.fi/computing/running/batch-job-partitions/)
- [PyTorch CSC:llä](https://docs.csc.fi/apps/pytorch/)
- [Koneoppimisen opas](https://docs.csc.fi/support/tutorials/ml-guide/)
- [Laskutus](https://docs.csc.fi/accounts/billing/) ja [HPC-laskutusyksiköt](https://docs.csc.fi/computing/hpc-billing/)
- [Maksuton käyttö](https://research.csc.fi/free-of-charge-use/)
- [Puhtin ja Mahtin korvaaminen](https://docs.csc.fi/support/tutorials/hpc-quick/) ja [HPCwire: Roihu avattiin tutkimuskäyttöön](https://www.hpcwire.com/off-the-wire/finlands-roihu-supercomputer-now-open-for-research-use/)
