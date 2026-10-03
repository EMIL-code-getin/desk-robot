# Solpalmtop

En Raspberry Pi-palmtop byggd efter Adafruits
[Mini Raspberry Pi Handheld Notebook](https://learn.adafruit.com/mini-raspberry-pi-handheld-notebook-palmtop).
Den laddas med solpanel via en powerbank, stänger av sig själv när batteriet tar
slut och har följande tillgängligt utan internet:

- **Wikipedia** på svenska, plus engelska handböcker om medicin och överlevnad (Kiwix)
- **Kartor** över Sverige (GPXSee med kartor från Mapsforge)
- **En överlevnadsguide** som öppnas med en ikon på skrivbordet:
  första hjälpen, läkemedel, skydd, vatten, eld, bär, svamp och signaler, med
  länkar till Wikipedia-artiklarna

```
Solpanel ──USB──► Powerbank ──USB-micro──► PowerBoost 1000C ──► LiPo + Pi
                                                │
                                              LBO ──diod──► GPIO26 (avstängning)
```

## 1. Inköpslista

Artikelnumren är Adafruits. I Sverige säljs Adafruit bland annat av Electrokit.
Priserna är ungefärliga.

### Datorn (från Adafruit-guiden)
| # | Del | Adafruit-nr | Ca pris |
|---|---|---|---|
| 1 | Raspberry Pi 3 Model B/B+ | 3055 | 450 kr |
| 1 | PiTFT Plus 3,5" pekskärm (480×320) | 2441 | 550 kr |
| 1 | Litet trådlöst tangentbord med styrplatta | 922 | 250 kr |
| 1 | PowerBoost 1000C | 2465 | 250 kr |
| 1 | LiPo-batteri 3,7 V 2000 mAh | 2011 | 150 kr |
| 1 | Skjutbrytare SPDT | 805 | 10 kr |
| 1 | **Microkort på 128 GB** (A1). Wikipedia och kartor tar mycket plats. | – | 200 kr |
| – | *Valfritt:* metallhögtalare 8 Ω | 1890 | 30 kr |
| – | Filament till skalet, tunn kabel, krympslang, skruvar M2,5 | – | 150 kr |

### Solladdning
| # | Del | Ca pris |
|---|---|---|
| 1 | Hopfällbar USB-solpanel på 15–21 W, gärna med automatisk omstart efter moln ("smart IC" eller "auto-restart") | 400–700 kr |
| 1 | Powerbank på 10 000 mAh med USB-C-ingång | 250–400 kr |
| 1 | Kort kabel från USB-A till micro-USB | 50 kr |

### Automatisk avstängning
| # | Del | Ca pris |
|---|---|---|
| 1 | Schottkydiod 1N5817 (eller BAT85) | 5 kr |
| – | Ca 10 cm tunn kabel | – |

### Verktyg
Lödkolv och tenn, avbitare, avisoleringstång, multimeter och tillgång till en 3D-skrivare.

**Totalt ca 2 700–3 200 kr.**

## 2. Koppla ihop

Bygg skalet och montera skärmen och tangentbordet enligt Adafruit-guiden.
Strömdelen kopplas så här:

```
LiPo ──JST──► PowerBoost 1000C
                 BAT/GND  (batteriet)
                 EN ──────── skjutbrytare ──── GND
                 5V ───────────────────────── Pi stift 2 (5V)
                 GND ──────────────────────── Pi stift 6 (GND)
                 LBO ──|<── diod ──────────── Pi stift 37 (GPIO26)
                       ↑ katoden (strecket) mot LBO
```

1. **Testa PowerBoost först.** Koppla in batteriet med JST-kontakten. Mät mellan
   5V och GND på PowerBoost-kortet med multimetern. Du ska få 5,0–5,2 V.
2. **Strömbrytaren.** Löd brytarens mittben till **EN** och ett av ytterbenen
   till **GND**. När EN är kopplad till GND är strömmen av. Slå av brytaren och
   kontrollera med multimetern att 5V-utgången nu är 0 V.
3. **Ström till Pi:n.** Löd en kabel från PowerBoost **5V** till Pi:ns **stift 2**
   och en från **GND** till **stift 6**. Skärmen täcker stiftlisten, så löd
   på undersidan av Pi:n, där stiften sticker igenom kortet.
   **Dubbelkolla polariteten innan du slår på strömmen.** Fel håll förstör Pi:n.
4. **Avstängningssignalen.** Löd diodens **katod** (sidan med strecket) till
   **LBO** på PowerBoost. Löd anoden via en kort kabel till Pi:ns **stift 37
   (GPIO26)**, också på undersidan. Skärmen använder inte GPIO26. Isolera med
   krympslang.
5. **Högtalaren** kopplas enligt kretsschemat i Adafruit-guiden.
6. **Laddning:** du laddar genom micro-USB-porten på PowerBoost.
   Gör ett hål för den i skalet om guidens skal inte redan har ett.

Stiftnumren räknas med stift 1 närmast microkortet, i den inre raden.
Stift 2, 4 och 6 ligger i den yttre raden, närmast kortkanten.
I den inre raden är stift 37 (GPIO26) näst sist och stift 39 (GND) sist.

## 3. Installera programmen

### 3.1 Operativsystem och skärm
1. Följ Adafruits guide för **PiTFT 3.5"** (avsnittet *Easy Install*) för att
   installera Raspberry Pi OS och skärmdrivrutinen. Använd den OS-version som
   Adafruits guide rekommenderar för just den här skärmen.
2. Anslut Pi:n till wifi och kör `sudo apt update && sudo apt full-upgrade`.

### 3.2 Hämta de här filerna till Pi:n
Öppna en terminal på Pi:n:

```bash
git clone --branch claude/nice-rubin-wqflj6 https://github.com/EMIL-code-getin/desk-robot.git
cd desk-robot/palmtop
```

Om repot är privat frågar git efter användarnamn och lösenord. Använd då en
[personlig åtkomsttoken](https://github.com/settings/tokens) som lösenord.
Annars kan du ladda ner repot som ZIP på en dator och kopiera mappen
`palmtop` till Pi:n med ett USB-minne.

### 3.3 Kör installationsskriptet
```bash
bash setup.sh
```

Skriptet frågar innan det laddar ner något och visar storleken och hur mycket
ledigt utrymme som finns kvar. Det gör följande:

1. Installerar `kiwix-tools` (offline-Wikipedia), `gpxsee` (kartor) och `gpiozero`.
2. Laddar ner den senaste versionen av:
   | Innehåll | Sparas som |
   |---|---|
   | Svenska Wikipedia, med eller utan bilder (du väljer) | `~/offline/zim/wikipedia_sv.zim` |
   | WikiMed, engelska medicinartiklar | `~/offline/zim/wikimed_en.zim` |
   | Post-disaster, engelska handböcker för kris och överlevnad | `~/offline/zim/post-disaster_en.zim` |
   | Water, engelska handböcker om vattenrening | `~/offline/zim/water_en.zim` |
3. Startar Kiwix som en tjänst på `http://localhost:8080`, som startar automatiskt vid varje uppstart.
4. Laddar ner kartan över Sverige till `~/offline/maps/sweden.map`. Ändra
   `MAPS="sweden"` överst i skriptet om du vill ha fler länder, till exempel
   `MAPS="sweden norway finland"`.
5. Kopierar överlevnadsguiden till `~/survival/` och lägger ikoner på
   skrivbordet: **Överlevnadsguide**, **Wikipedia (offline)** och **Kartor (offline)**.
6. Installerar avstängningen vid lågt batteri (`lowbatt.py`) som en tjänst.

**Om det tar lång tid:** svenska Wikipedia med bilder är många GB, och Pi 3
har långsamt wifi. Låt den ladda över natten. Skriptet fortsätter där det slutade
om du kör det igen. Du kan också ladda ner filerna från
<https://download.kiwix.org/zim/> på en snabbare dator och kopiera dem till
`~/offline/zim/` med de namn som står i tabellen ovan.

### 3.4 Testa
- **Wikipedia:** dubbelklicka på *Wikipedia (offline)*. Bibliotekssidan ska visa de nedladdade böckerna.
- **Överlevnadsguiden:** dubbelklicka på *Överlevnadsguide* och tryck på en länk, till exempel *Blåbär*.
  Artikeln ska öppnas från `localhost:8080`. Den lilla länken *webb* öppnar samma artikel på internet.
- **Kartor:** starta *Kartor (offline)* och välj *Sweden* i menyn **Map**. Om
  den inte finns där väljer du **Map → Load map…** och öppnar `~/offline/maps/sweden.map`.
- **Avstängningen:** koppla stift 37 till GND (stift 39) med en kopplingstråd i
  mer än 10 sekunder. Pi:n ska visa en varning och stänga av sig.

Om skrivbordet frågar om du vill köra en genväg väljer du *Kör* (Execute).

## 4. Ladda med sol

1. Fäll ut panelen i direkt sol, vinklad rakt mot solen. Vrid den
   ungefär varannan timme.
2. Koppla powerbanken till panelen. Skugga gärna powerbanken, eftersom värme
   minskar batteriernas livslängd.
3. Koppla palmtoppen till powerbanken. Det går att använda den samtidigt som den laddas.

Palmtoppen förbrukar 3–4 W och batteriet rymmer ca 7 Wh, vilket räcker
**1,5–2 timmar**. Det går att få ut ungefär tre fulla laddningar ur en
powerbank på 10 000 mAh.

## 5. Felsökning

| Problem | Gör så här |
|---|---|
| Wikipedia-länkarna fungerar inte | `sudo systemctl status kiwix` – finns det `.zim`-filer i `~/offline/zim/`? Starta om med `sudo systemctl restart kiwix`. |
| En artikel saknas ("not found") | Rubriken kan vara olika i olika versioner. Använd sökfältet högst upp i Kiwix. |
| Pi:n stänger av sig för tidigt | Öka `hold_time` i `/usr/local/bin/lowbatt.py` och kör `sudo systemctl restart lowbatt`. |
| Blixtsymbol eller varning för låg spänning på skärmen | Kabeln mellan PowerBoost och Pi:n är för tunn eller för lång. Använd kortare och grövre kabel (22 AWG). |
| Solpanelen slutar ladda när det blir molnigt | Normalt för USB-paneler. Powerbanken jämnar ut det. Välj en panel med automatisk omstart. |

## Filer

| Fil | Vad |
|---|---|
| `setup.sh` | Installerar allt (kör på Pi:n) |
| `lowbatt.py` | Stänger av vid lågt batteri (GPIO26) |
| `survival/index.html` | Överlevnadsguiden. Fungerar i vilken webbläsare som helst, även utan Pi:n. |

**Överlevnadsguiden är en minneslista och ersätter inte en kurs i första hjälpen.**
Ät aldrig bär, svamp eller växter som du inte säkert känner igen.
