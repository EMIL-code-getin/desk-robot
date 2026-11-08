# Stream deck: 9 tangenter, vridratt och OLED-display

En makropanel byggd i **Macropad**-chassit från MakerWorld (3×3 tangenter,
ratt och 0,96"-display). Hjärnan är en **Seeed XIAO ESP32-C3** och displayen
kommer från **SunFounder Ultimate Sensor Kit**. Panelen kopplar upp sig
trådlöst som ett **Bluetooth-tangentbord med mediaknappar**, så datorn behöver
inga drivrutiner eller program. Displayen visar vad varje knapp gör.

```
        bak (USB-C)
   [ OLED ]      ( ratt )
   +---------+---------+---------+
   | Bambu   | YouTube |  Gmail  |   1 2 3
   +---------+---------+---------+
   | Kopiera | Klistra |  Mute   |   4 5 6
   +---------+---------+---------+
   | Deafen  |  Ångra  |  PrtSc  |   7 8 9
   +---------+---------+---------+
        fram          vrid = volym, klick = ljud av
```

**Varför Bluetooth och inte USB?** ESP32-C3 kan inte vara ett USB-tangentbord:
USB-porten används bara för programmering och ström. Bluetooth LE fungerar
direkt i Windows, macOS, Linux, Android och iOS.

## Innehåll

```
stream-deck/
├── firmware/
│   ├── stream_deck/              Arduino-skiss (öppna stream_deck.ino)
│   │   ├── stream_deck.ino
│   │   ├── config.h              ← pinnar, namn, display och vad varje knapp gör
│   │   ├── keycodes.h            tangentkoder (KEY_F13, MEDIA_VOL_UP ...)
│   │   └── deck.cpp, ble_hid.cpp, display.cpp …
│   └── platformio.ini            om du hellre använder PlatformIO
├── docs/pinout.html             detaljerad pinout med bilder
└── case/
    ├── xiao_tray.scad       bricka som håller XIAO:n i chassits kortficka
    └── stl/xiao_tray.stl
```

Själva chassit (Housing, Top_Case, Key_Cap, Knob) finns inte här. Det är
Macropad-modellen från MakerWorld, som du redan har skrivit ut.

## Det här behöver du

| Antal | Del | Kommentar |
|---|---|---|
| 1 | Seeed Studio XIAO ESP32C3 **med antennen XIAO FPC Antenna A-01** | C3:an har ingen inbyggd antenn. Utan antennen fungerar Bluetooth knappt. |
| 1 | OLED-displayen från SunFounder Ultimate Sensor Kit | 0,96", 128×64, SSD1306, I2C (GND, VCC, SCL, SDA) |
| 9 | Mekaniska switchar, MX-kompatibla | De snäpper fast i locket. |
| 1 | Rotary encoder-modul (KY-040-typ) med CLK, DT, SW, + och GND | Ratten från MakerWorld-filen passar encoderns 6 mm D-axel. |
| 4 | M2-skruvar, ca 8 mm | För att skruva ihop locket och huset. |
| – | Tunn kopplingstråd (26–28 AWG), lödpenna, lite smältlim | |

## 1. Skriv ut brickan för XIAO:n

Huset har en ficka för kortet som originalet använder (DFRobot Beetle RP2350,
25 × 20,5 mm). XIAO:n är mindre (21 × 17,8 mm). Brickan `case/stl/xiao_tray.stl`
fyller ut fickan, trycker XIAO:n mot bakväggen och lyfter den så att USB-C-kontakten
hamnar mitt i hålet.

Skriv ut den platt, som den ligger, utan support (PLA, 0,2 mm). Det tar ett par
minuter.

> Hamnar USB-kontakten för högt eller för lågt mot hålet? Ändra `lift` i
> `case/xiao_tray.scad` (standard 1,0 mm) och exportera igen:
>
> ```bash
> openscad -o stl/xiao_tray.stl xiao_tray.scad
> ```

## 2. Koppla

XIAO ESP32C3 har bara 11 pinnar, men 9 tangenter, encodern och displayen skulle
behöva 14. Tangenterna kopplas därför som en **matris med 3 rader och
3 kolumner**. Då räcker 6 pinnar till alla nio tangenterna.

| Funktion | XIAO-pinne |
|---|---|
| Rad 1 (tangent 1, 2, 3, närmast displayen) | D10 |
| Rad 2 (tangent 4, 5, 6) | D7 |
| Rad 3 (tangent 7, 8, 9) | D6 |
| Kolumn 1 (tangent 1, 4, 7, vänster) | D0 |
| Kolumn 2 (tangent 2, 5, 8) | D8 |
| Kolumn 3 (tangent 3, 6, 9, höger) | D9 |
| Encoder CLK / DT | D1 / D2 |
| Encoder SW | D3 |
| OLED SDA / SCL | D4 / D5 |
| OLED VCC och encoder + | **3V3** (inte 5V) |
| OLED GND och encoder GND | GND |

> **Detaljerad pinout med bilder:** öppna [`docs/pinout.html`](docs/pinout.html)
> i webbläsaren. Där finns XIAO:ns alla pinnar, matrisen sedd både ovanifrån
> och underifrån (när du löder), encodern och displayen.

### Tangentmatrisen

Varje switch har två ben. Det ena går till tangentens **kolumn**, det andra
direkt till tangentens **rad**. Inga dioder behövs.

```
  kolumntråd ──[ switch ]── radtråd

  Tangent:   1    2    3    4    5    6    7    8    9
  Kolumn:    D0   D8   D9   D0   D8   D9   D0   D8   D9
  Rad:       D10  D10  D10  D7   D7   D7   D6   D6   D6
```

Praktiskt: dra en isolerad tråd lodrätt genom varje **kolumn** och en
vågrätt genom varje **rad**. Skala bara av där tråden ska lödas, så att rad-
och kolumntrådarna inte rör varandra där de korsas. Det spelar ingen roll
vilket av switchens två ben som går till kolumnen.

**Utan dioder** kan tre nedtryckta tangenter som bildar ett "L" (till exempel
1, 2 och 4) få en fjärde (5) att se nedtryckt ut. Koden känner igen det
mönstret och ignorerar den tredje tangenten tills du släpper en, så ingen fel
tangent skickas. Två tangenter samtidigt, eller flera i samma rad eller
kolumn, fungerar alltid. Lägger du till dioder senare (1N4148, svarta ringen
mot raden), sätt `MATRIX_HAS_DIODES true` i `config.h`.

### Encoder och display

```
  Encoder-modul:   CLK ── D1    DT ── D2    SW ── D3    + ── 3V3    GND ── GND
  OLED:            GND ── GND   VCC ── 3V3  SCL ── D5   SDA ── D4
```

Encoderns **+ ska till 3V3**, inte 5V. Modulen har motstånd från CLK och DT
till +, så 5V där skulle lägga 5 V på XIAO:ns pinnar.

### Montering

1. **Switcharna:** tryck fast de nio switcharna i locket från ovansidan.
2. **Encodern:** stick upp axeln genom hålet underifrån och dra åt muttern på
   ovansidan. Locket har också två skruvtappar på var sin sida om hålet
   (25,5 mm isär); passar modulens hål kan du skruva fast den där.
3. **Displayen:** locket har fyra små piggar runt displayfönstret, avsedda för
   en vanlig 0,96"-modul med hålen ca 23 × 23,5 mm isär. Trä displayen på
   piggarna med **stiftlisten mot bakkanten** (USB-sidan). Lås den med en
   droppe smältlim, eller smält piggtopparna försiktigt med lödpennan.
   Om hålen i SunFounder-modulen inte passar piggarna: klipp av piggarna,
   centrera glaset i fönstret och limma modulen.
4. **XIAO:n:** lägg brickan i kortfickan med den öppna änden mot USB-hålet och
   tryck ned XIAO:n i brickan med USB-C först.
5. **Antennen (FPC Antenna A-01):** tryck fast den lilla runda kontakten på
   XIAO:ns u.FL-uttag tills det klickar. Dra av skyddspappret och klistra den
   platta antennen plant på insidan av en sidovägg, så långt från trådarna som
   möjligt. Böj inte kabeln skarpt vid kontakten.
6. **Löd** enligt tabellen ovan.
7. **Ladda upp koden och testa** (steg 3) innan du skruvar ihop.
8. Skruva ihop locket och huset med de fyra M2-skruvarna och sätt på
   keycaps och ratt.

## 3. Ladda upp koden (Arduino IDE)

### Förbered Arduino IDE (en gång)

1. Installera [Arduino IDE 2](https://www.arduino.cc/en/software).
2. **Kortpaketet för ESP32:** öppna **File → Preferences** och klistra in den
   här adressen i *Additional boards manager URLs*:

   ```
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```

   Öppna sedan **Tools → Board → Boards Manager**, sök på `esp32` och
   installera **esp32 by Espressif Systems**, version **3.x**.
3. **Biblioteken:** öppna **Tools → Manage Libraries** och installera:
   - **NimBLE-Arduino** av h2zero, version **2.x** (Bluetooth)
   - **U8g2** av oliver (displayen)

### Ladda upp

1. Öppna `firmware/stream_deck/stream_deck.ino`. Alla filer i mappen öppnas
   som flikar. Det du vill ändra finns i fliken **config.h**.
2. Sätt i XIAO:n med USB-C.
3. Välj under **Tools**:
   - **Board:** *esp32 → XIAO_ESP32C3*
   - **Port:** den COM-port som dyker upp när du sätter i XIAO:n
   - **USB CDC On Boot:** *Enabled*
4. Klicka på pilen (**Upload**). Första gången tar kompileringen någon minut.
5. Öppna **Tools → Serial Monitor** (115200 baud) för att se loggen: knapptryck,
   anslutning, lager och `[oled] ok` om displayen hittas.

> Om uppladdningen inte startar, eller porten inte syns: håll in **BOOT** på
> XIAO:n, tryck på **RESET**, släpp BOOT och försök igen.

> **USB CDC On Boot** måste vara *Enabled*. Annars går loggen till pinnarna
> D6/D7, som här används av tangentmatrisen. Panelen fungerar ändå, men
> Serial Monitor blir tom.

<details>
<summary>PlatformIO i stället för Arduino IDE</summary>

`firmware/platformio.ini` bygger samma skissmapp. Öppna mappen `firmware` i
VS Code med PlatformIO och klicka på *Upload*, eller kör:

```bash
cd stream-deck/firmware
```

```bash
pio run -t upload
```

</details>

## 4. Para ihop med datorn

1. Ge panelen ström via USB-C. På displayen står **Söker BT**.
2. På datorn: **Inställningar → Bluetooth → Lägg till enhet**. Välj
   **Stream Deck**.
3. Klart. I displayens hörn står nu **1/3 BT**. Nästa gång ansluter panelen
   automatiskt.

**Byta dator / glömma gamla parkopplingar:** håll in tangent 1 och ratten
samtidigt när du ger panelen ström. Displayen visar *Parkopplingar raderade*.
Ta också bort enheten i datorns Bluetooth-lista innan du parar om.

## 5. Använda den

Displayen visar lagrets namn, Bluetooth-status och namnet på alla nio
tangenter. Tangenten du håller in visas inverterad. Längst ned står vad ratten
gör.

Panelen har tre **lager**. **Håll in ratten i 0,6 s** för att byta lager. Valt
lager sparas även när strömmen bryts. Skärmen släcks efter 10 minuter utan
användning och tänds igen när du trycker eller vrider.

| | Lager 1 "Apps" | Lager 2 "Media" | Lager 3 "Redigera" |
|---|---|---|---|
| Tangent 1 | **Bambu Studio** (startas via sök) | Föregående låt | Kopiera |
| Tangent 2 | **YouTube** (i webbläsaren) | Play/paus | Klistra in |
| Tangent 3 | **Gmail** (i webbläsaren) | Nästa låt | Klipp ut |
| Tangent 4 | **Kopiera** (Ctrl+C) | Mikrofon av/på i Teams | Spara |
| Tangent 5 | **Klistra in** (Ctrl+V) | Kamera av/på i Teams | Sök |
| Tangent 6 | **Mute i Discord** (F13) | Stopp | Markera allt |
| Tangent 7 | **Fullmute i Discord** (F14) | Miniräknare | Ny flik |
| Tangent 8 | Ångra (Ctrl+Z) | Webbläsare | Stäng flik |
| Tangent 9 | **Print Screen** | E-post | Visa skrivbordet |
| Vrid höger / vänster | Volym upp / ner | Volym upp / ner | Gör om / ångra |
| Klick på ratten | Ljud av | Play/paus | Enter |

### Ställ in datorn (en gång)

**Bambu Studio, YouTube och Gmail** behöver ingen inställning.
- **Tangent 1** trycker på Windows-tangenten, skriver *bambu studio* och trycker
  Enter, precis som när du söker i Start-menyn. Är programmet redan öppet
  växlar Windows till det.
- **Tangent 2 och 3** trycker Win+R, skriver webbadressen och trycker Enter.
  Sidan öppnas i din vanliga webbläsare.

Låt bli att trycka på andra tangenter de 1–2 sekunder det tar.

**Mute och fullmute i Discord** behöver en inställning i Discord. Discords egna
kortkommandon (Ctrl+Shift+M och Ctrl+Shift+D) fungerar bara när
Discord-fönstret är aktivt. Panelen skickar därför F13 och F14, som inte finns
på vanliga tangentbord, och du lägger in dem som tangentbindningar i Discord. Då
fungerar de även när du sitter i Bambu Studio eller ett spel.

1. Discord → **Användarinställningar** (kugghjulet) → **Tangentbindningar** →
   **Lägg till en tangentbindning**.
2. Välj åtgärden för att slå av och på mikrofonen (**Toggle Mute** i engelska
   Discord). Klicka i tangentfältet och tryck på **tangent 6** på panelen.
   Där ska det stå F13.
3. Lägg till en bindning till med åtgärden för att slå av och på allt ljud
   (**Toggle Deafen**). Klicka i fältet och tryck på **tangent 7**. Där ska
   det stå F14.

**Print Screen** (tangent 9) gör det som Print Screen-tangenten är inställd
på i Windows. I Windows 11 öppnas skärmklippverktyget som standard. Vill du i
stället kopiera hela skärmen direkt: **Inställningar → Hjälpmedel →
Tangentbord → Använd Print Screen-knappen för att öppna skärmbild**, stäng av.

### Ändra knapparna

Allt finns i fliken `config.h` (filen `firmware/stream_deck/config.h`), i listan `LAYERS`. Den första texten
är det som visas på displayen (högst 7 tecken; å, ä och ö fungerar):

```cpp
KEY("PrtSc", KEY_PRINTSCREEN)              // en tangent
COMBO("Kopiera", MOD_CTRL, KEY_C)          // tangentkombination
MEDIA("Play", MEDIA_PLAY_PAUSE)            // mediaknapp
SEARCH("Bambu", "bambu studio")            // startar ett program via Windows-sökningen
RUN("YouTube", "https://www.youtube.com")  // Win+R: öppnar en webbadress, ett program eller en mapp
TEXT("Hej", "hej\n")                       // skriver text
NEXT_LAYER("Lager")                        // byt lager
NONE                                       // gör ingenting
```

Du kan lägga till fler lager genom att kopiera ett block i `LAYERS`.
Alla tangentkoder finns i `keycodes.h`. Ladda upp koden igen efter varje ändring.

> `RUN`, `SEARCH` och `TEXT` skriver tecken som om de vore tangenttryck, så de
> måste veta vilken tangentbordslayout Windows använder. Standard är svensk
> (`KEYBOARD_LAYOUT_SE true` i `config.h`). Bokstäver, siffror och vanliga
> tecken som `: / . - _ ? = & @` fungerar, men inte å, ä och ö.
> Displaytexterna har inte den begränsningen.

## Felsökning

| Problem | Lösning |
|---|---|
| Displayen är svart | Kolla VCC till **3V3**, GND, och att SDA/SCL inte är förväxlade (D4 = SDA, D5 = SCL). I `pio device monitor` står `[oled] ok` eller `no display at 0x3C`. Panelen fungerar även utan display. |
| Texten är upp och ned | Sätt `OLED_ROTATE_180 true` i `config.h`. |
| Fel tangent reagerar / en hel rad eller kolumn är död | Kolla matristrådarna. `key N down` i loggen visar vilken tangent koden ser. Byter två tangenter plats har du förväxlat två rad- eller kolumntrådar. |
| En tangent reagerar inte när du redan håller in två andra | Normalt utan dioder: tre tangenter i ett "L" spärras för att undvika spöktryck. Släpp en av de andra. |
| En tangent verkar alltid vara nedtryckt | En rad- och en kolumntråd rör varandra där de korsas. |
| Ratten går åt fel håll | Sätt `ENC_REVERSE true` i `config.h`. |
| Ratten hoppar två steg per klick / behöver två klick per steg | Växla `ENC_HALF_STEP`. |
| Bluetooth tappar anslutningen eller syns knappt | Antennen sitter inte i, eller ligger tryckt mot trådarna. |
| Panelen syns inte i Bluetooth-listan | Den är redan parad med en annan enhet. Rensa parkopplingar (tangent 1 + ratt vid start). |
| Ansluten men inget händer i Windows | Ta bort enheten i Bluetooth-inställningarna och para om. Det behövs också efter att du ändrat `DEVICE_NAME`. |
| Bambu Studio startar inte, eller fel program startar | Windows-sökningen hann inte hitta programmet. Öka `SEARCH_RESULT_MS` (och vid behov `SEARCH_OPEN_MS`) i `config.h`. Testa också att själv trycka på Windows-tangenten och skriva *bambu studio*: kommer Bambu Studio överst? |
| Konstiga tecken i stället för YouTube-/Gmail-adressen | Fel tangentbordslayout. `KEYBOARD_LAYOUT_SE` ska vara `true` om Windows använder svenskt tangentbord. |
| Kör-rutan öppnas men adressen skrivs inte klart | Öka `RUN_DIALOG_MS` eller `TYPE_MS` i `config.h`. |
| Mute/fullmute i Discord gör ingenting | Bindningen saknas i Discord. Lägg till F13/F14 under Tangentbindningar (se ovan). Om Discord inte vill ta emot F13 när du trycker, byt till `COMBO("Mute", MOD_CTRL \| MOD_SHIFT \| MOD_ALT, KEY_M)` i `config.h`. |
| En viss tangent gör ingenting | Titta på displayen när du trycker. Blir rutan **inte** inverterad når trycket aldrig fram till XIAO:n: kolla lödningen och rad- och kolumntråden för den tangenten. Blir den inverterad är kopplingen rätt, och felet ligger i vad tangenten skickar. |
| Tangenterna gör plötsligt något annat | Du har bytt lager genom att hålla in ratten. Läs lagrets namn uppe till vänster på displayen och håll in ratten tills det står "Apps". |
