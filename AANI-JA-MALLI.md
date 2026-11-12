# Jooseppi ja Justiina: mallin lisenssi ja äänten käyttöehdot

*English summary at the end.*

Tämä asiakirja koskee kahta ääntä ja niiden yhteistä mallia:

- **Jooseppi** on miesääni. Se koostuu Juuso Kojon äänellä hienosäädetyistä mallin painoista (checkpoint-tiedostot) ja hänen äänensä viitenäytteistä.
- **Justiina** on naisääni. Se koostuu naispuhujan viitenäytteistä, joita käytetään samojen painojen kanssa. Puhuja on antanut äänensä käyttöön samoin ehdoin kuin Jooseppi-ääni, ja hän pysyy nimettömänä.

Repositorion lähdekoodia koskee [LICENSE](LICENSE) (MIT). Painot ja ääninäytteet eivät ole tässä repositoriossa, vaan ne jaetaan erikseen. Nämä ehdot koskevat niitä kaikkialla, missä ne jaetaan.

Ehdoissa on kaksi osaa. Mallin painot ovat perusmallin muokattu versio, ja niitä koskee perusmallin tekijänoikeuslisenssi. Ääni on henkilöön liittyvä oikeus, jota Creative Commons -lisenssit eivät kata, joten äänten käytöstä annetaan erillinen lupa. Käyttäjän on noudatettava molempia osia.

## 1. Mallin painot: CC BY-NC 4.0

Hienosäädetyt painot julkaistaan lisenssillä [Creative Commons Nimeä-EiKaupallinen 4.0](https://creativecommons.org/licenses/by-nc/4.0/deed.fi), koska perusmalli on julkaistu samalla lisenssillä.

Mallin ketju:

1. [SWivid/F5-TTS](https://huggingface.co/SWivid/F5-TTS), CC BY-NC 4.0
2. Suomenkielinen hienosäätö [AsmoKoskinen/F5-TTS_Finnish_Model](https://huggingface.co/AsmoKoskinen/F5-TTS_Finnish_Model), CC BY-NC 4.0
3. Hienosäätö Juuso Kojon äänellä, CC BY-NC 4.0. Samoja painoja käytetään sekä Jooseppi- että Justiina-äänessä.

**Nimeäminen.** Kun käytät mallia tai julkaiset sillä tuotettua puhetta, mainitse käyttämäsi ääni esimerkiksi näin:

> Puhe on tuotettu tekoälyllä. Ääni: Jooseppi (Juuso Kojo), F5-TTS Finnish -malliin perustuva, CC BY-NC 4.0.

> Puhe on tuotettu tekoälyllä. Ääni: Justiina, F5-TTS Finnish -malliin perustuva, CC BY-NC 4.0.

## 2. Äänten käyttölupa

Jooseppi- ja Justiina-ääntä ja niiden viitenäytteitä saa käyttää seuraaviin tarkoituksiin:

- opetukseen ja opetusmateriaaleihin
- tutkimukseen
- maksuttomaan koulutukseen
- edellisten tarkoitusten mukaisten materiaalien julkaisemiseen, myös verkossa

Luvan antavat äänten puhujat. Justiina-äänen puhujan puolesta luvasta ilmoittaa Juuso Kojo.

**Ääniä ei saa käyttää:**

1. esiintymiseen äänen puhujana tai väittämiseen, että puhuja on sanonut jotain, mitä hän ei ole sanonut
2. Justiina-äänen puhujan henkilöllisyyden selvittämiseen tai paljastamiseen
3. kaupalliseen käyttöön, kuten myytäviin tuotteisiin ja palveluihin, maksulliseen koulutukseen tai mainontaan
4. poliittiseen tai uskonnolliseen vaikuttamiseen tai vaalimainontaan
5. harhaanjohtamiseen, huijaamiseen, kunnianloukkaukseen, häirintään tai muuhun lainvastaiseen tai loukkaavaan sisältöön
6. äänitunnistukseen perustuvien tunnistautumis- tai turvajärjestelmien ohittamiseen
7. uusien äänimallien kouluttamiseen, jotka jäljittelevät näitä ääniä, paitsi tutkimuksessa, jossa mallia ei jaeta eteenpäin

**Merkintä.** Kun tuotettua puhetta julkaistaan tai sitä esitetään muille, siitä on kerrottava, että puhe on tekoälyn tuottamaa. Kohdassa 1 annettu nimeämisteksti riittää tähän.

**Aineisto.** Hienosäädössä käytettyjä alkuperäisiä nauhoituksia ei jaeta, eikä tämä lupa koske niitä.

**Luvan muuttaminen ja peruminen.** Lupaa voidaan muuttaa tai se voidaan perua uusien käyttöjen osalta ilmoittamalla siitä tässä tiedostossa. Muutos voi koskea jompaakumpaa ääntä tai molempia. Ennen ilmoitusta tehdyt ja julkaistut opetus- ja tutkimusmateriaalit saavat jäädä käyttöön.

**Kaupallinen käyttö.** Kaupallinen käyttö ei ole mahdollista tällä mallilla, koska perusmallin lisenssi kieltää sen. Kaupallisesta käytöstä voi sopia erikseen eri perusmallilla toteutetusta versiosta.

Yhteystiedot molempia ääniä koskevissa asioissa: Juuso Kojo, GitHub [@juusokojo](https://github.com/juusokojo)

---

## English summary

Two voices share one model:

- **Jooseppi** (male) = model weights fine-tuned on Juuso Kojo's voice, and reference recordings of his voice.
- **Justiina** (female) = reference recordings of a female speaker, used with the same weights. The speaker has given the same permission and remains anonymous.

The weights and recordings are distributed separately, not in this repository. The source code is MIT-licensed (see [LICENSE](LICENSE)).

1. **Model weights:** [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/), inherited from [SWivid/F5-TTS](https://huggingface.co/SWivid/F5-TTS) and [AsmoKoskinen/F5-TTS_Finnish_Model](https://huggingface.co/AsmoKoskinen/F5-TTS_Finnish_Model).
2. **Voice permission:** CC licenses do not cover personality rights, so the speakers give a separate permission. You may use both voices through this model for teaching, research and free education, including published materials.
3. **Not allowed:** impersonating a speaker or attributing words to them; identifying or revealing the Justiina speaker; commercial use; political or religious campaigning; deception, fraud, defamation or harassment; defeating voice-based authentication; training further models that imitate these voices, except in research where the model is not distributed.
4. **Disclosure:** Published or presented speech must be disclosed as AI-generated.
5. **Recordings:** The original training recordings are not distributed.
6. **Changes:** The permission may be changed or withdrawn for new uses, for either voice, by updating this file. Materials published before that may remain in use.
7. **Contact** for both voices: Juuso Kojo, GitHub [@juusokojo](https://github.com/juusokojo).
