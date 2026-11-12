# Jooseppi-ääni: mallin lisenssi ja äänen käyttöehdot

*English summary at the end.*

Tämä asiakirja koskee **Jooseppi-ääntä**, eli Juuso Kojon äänellä tehtyjä seuraavia osia:

- hienosäädettyjä mallin painoja (checkpoint-tiedostot)
- viitenäytteitä, joita malli tarvitsee puheen tuottamiseen

Repositorion lähdekoodia koskee [LICENSE](LICENSE) (MIT). Painot ja ääninäytteet eivät ole tässä repositoriossa, vaan ne jaetaan erikseen. Nämä ehdot koskevat niitä kaikkialla, missä ne jaetaan.

Ehdoissa on kaksi osaa. Mallin painot ovat perusmallin muokattu versio, ja niitä koskee perusmallin tekijänoikeuslisenssi. Ääni on henkilöön liittyvä oikeus, jota Creative Commons -lisenssit eivät kata, joten sen käytöstä annetaan erillinen lupa. Käyttäjän on noudatettava molempia osia.

## 1. Mallin painot: CC BY-NC 4.0

Hienosäädetyt painot julkaistaan lisenssillä [Creative Commons Nimeä-EiKaupallinen 4.0](https://creativecommons.org/licenses/by-nc/4.0/deed.fi), koska perusmalli on julkaistu samalla lisenssillä.

Mallin ketju:

1. [SWivid/F5-TTS](https://huggingface.co/SWivid/F5-TTS), CC BY-NC 4.0
2. Suomenkielinen hienosäätö [AsmoKoskinen/F5-TTS_Finnish_Model](https://huggingface.co/AsmoKoskinen/F5-TTS_Finnish_Model), CC BY-NC 4.0
3. Jooseppi-ääni: hienosäädetty Juuso Kojon äänellä, CC BY-NC 4.0

**Nimeäminen.** Kun käytät mallia tai julkaiset sillä tuotettua puhetta, mainitse esimerkiksi näin:

> Puhe on tuotettu tekoälyllä. Ääni: Jooseppi (Juuso Kojo), F5-TTS Finnish -malliin perustuva, CC BY-NC 4.0.

## 2. Äänen käyttölupa

Annan luvan käyttää ääntäni Jooseppi-äänen ja sen viitenäytteiden avulla seuraaviin tarkoituksiin:

- opetukseen ja opetusmateriaaleihin
- tutkimukseen
- maksuttomaan koulutukseen
- edellisten tarkoitusten mukaisten materiaalien julkaisemiseen, myös verkossa

**Ääntäni ei saa käyttää:**

1. esiintymiseen minuna tai väittämiseen, että olen sanonut jotain, mitä en ole sanonut
2. kaupalliseen käyttöön, kuten myytäviin tuotteisiin ja palveluihin, maksulliseen koulutukseen tai mainontaan
3. poliittiseen tai uskonnolliseen vaikuttamiseen tai vaalimainontaan
4. harhaanjohtamiseen, huijaamiseen, kunnianloukkaukseen, häirintään tai muuhun lainvastaiseen tai loukkaavaan sisältöön
5. äänitunnistukseen perustuvien tunnistautumis- tai turvajärjestelmien ohittamiseen
6. uusien äänimallien kouluttamiseen, jotka jäljittelevät ääntäni, paitsi tutkimuksessa, jossa mallia ei jaeta eteenpäin

**Merkintä.** Kun tuotettua puhetta julkaistaan tai sitä esitetään muille, siitä on kerrottava, että puhe on tekoälyn tuottamaa. Nimeämisessä kohdassa 1 annettu teksti riittää tähän.

**Aineisto.** Hienosäädössä käytettyjä alkuperäisiä nauhoituksia ei jaeta, eikä tämä lupa koske niitä.

**Luvan muuttaminen ja peruminen.** Voin muuttaa tai perua luvan uusien käyttöjen osalta ilmoittamalla siitä tässä tiedostossa. Ennen ilmoitusta tehdyt ja julkaistut opetus- ja tutkimusmateriaalit saavat jäädä käyttöön.

**Kaupallinen käyttö.** Kaupallinen käyttö ei ole mahdollista tällä mallilla, koska perusmallin lisenssi kieltää sen. Kaupallisesta käytöstä voi sopia erikseen eri perusmallilla toteutetusta versiosta.

Yhteystiedot: Juuso Kojo, GitHub [@juusokojo](https://github.com/juusokojo)

---

## English summary

**Jooseppi voice** = model weights fine-tuned on Juuso Kojo's voice, and the reference recordings used with them. The weights and recordings are distributed separately, not in this repository. The source code is MIT-licensed (see [LICENSE](LICENSE)).

1. **Model weights:** [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/), inherited from [SWivid/F5-TTS](https://huggingface.co/SWivid/F5-TTS) and [AsmoKoskinen/F5-TTS_Finnish_Model](https://huggingface.co/AsmoKoskinen/F5-TTS_Finnish_Model).
2. **Voice permission:** CC licenses do not cover personality rights, so I give a separate permission. You may use my voice through this model for teaching, research and free education, including published materials.
3. **Not allowed:** impersonating me or attributing words to me; commercial use; political or religious campaigning; deception, fraud, defamation or harassment; defeating voice-based authentication; training further models that imitate my voice, except in research where the model is not distributed.
4. **Disclosure:** Published or presented speech must be disclosed as AI-generated.
5. **Recordings:** The original training recordings are not distributed.
6. **Changes:** I may change or withdraw the permission for new uses by updating this file. Materials published before that may remain in use.
