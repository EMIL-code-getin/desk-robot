# Offline-USB

En USB-sticka med Wikipedia, överlevnadsguider och svenska nödkort som fungerar
utan internet. Sätt i den i en dator med Windows, macOS eller Linux, dubbelklicka
en fil, och biblioteket öppnas i webbläsaren. Mobiler på samma wifi eller hotspot
kan läsa samtidigt.

Allt innehåll är öppna [Kiwix](https://kiwix.org)-arkiv (`.zim`). De kan också
läsas direkt med Kiwix-appen på mobilen, utan dator.

## Bygg stickan

Gör det nu, medan du har internet. Det behövs bara Python 3.10 eller nyare.

1. Formatera stickan som **exFAT** (FAT32 klarar inte filer över 4 GB).
2. Kör byggskriptet. Det visar vad som hämtas och hur stort det är, och frågar
   innan det börjar:

   ```
   python build_usb.py --target E:\ --tier lite                 # Windows
   python3 build_usb.py --target /Volumes/OFFLINE --tier lite   # Mac
   python3 build_usb.py --target /media/$USER/OFFLINE --tier standard
   ```

3. Testa: starta `START-WINDOWS.bat`, `START-MAC.command` eller `START-LINUX.sh`
   från stickan och öppna några artiklar, även från mobilen.

Kör samma kommando igen när du vill uppdatera. Färdiga filer hoppas över, avbrutna
nedladdningar fortsätter där de slutade, och nya utgåvor ersätter de gamla.
Varje fil kontrolleras mot den SHA-256 som Kiwix publicerar.

| Nivå | Sticka | Innehåll |
| --- | --- | --- |
| `lite` | 16 GB | Svenska Wikipedia (ingresser), svenska Wikivoyage, första hjälpen, vatten, mat, efter en katastrof, knopar, Wikipedia Medicine, Appropedia |
| `standard` | 64 GB | Allt i lite, men hela svenska Wikipedia (utan bilder), plus Wiktionary, Wikibooks, MDWiki, iFixit, Energypedia, engelska Wikivoyage, Stack Exchange (hus, friluftsliv, matlagning) och engelska Wikipedia (ingresser) |
| `full` | 256 GB+ | Allt i standard, men hela svenska och engelska Wikipedia med bilder |

Storlekarna ändras med varje utgåva. Kör med `--dry-run` för att se exakta siffror
och om allt får plats.

**Fler val**

| Val | Gör |
| --- | --- |
| `--lang sv` | Bara svenska arkiv (standard är `sv,en`). |
| `--include gutenberg-en` | Lägg till något ur katalogen, t.ex. Project Gutenberg (~200 GB). |
| `--exclude wikipedia-en-mini` | Hoppa över något. |
| `--list` | Visa hela katalogen med id:n. |
| `--dry-run` | Visa planen, hämta inget. |
| `--no-verify` | Hoppa över SHA-256-kontrollen (snabbare på långsamma stickor). |

Katalogen finns i [`catalog.json`](catalog.json). Lägg till fler arkiv där: allt
på [download.kiwix.org/zim](https://download.kiwix.org/zim/) fungerar. Ett arkiv
som inte finns på servern hoppas över med en varning. Egna `.zim`-filer som du lägger
i `library/` kommer också med i biblioteket.

## Vad som hamnar på stickan

```
START-WINDOWS.bat     START-MAC.command     START-LINUX.sh     LÄS-MIG.txt
portal/      startsidan: nödkort och länkar till biblioteket, öppnas även utan server
library/     .zim-arkiven
kiwix/       kiwix-serve för win, mac-arm64, mac-x64, linux-x64, linux-arm64
egna-filer/  dina egna PDF:er och dokument
manifest.json
```

Portalen har nödnummer, varningssignaler (VMA, beredskapslarm, flyglarm), HLR,
kraftig blödning, vatten, värme och strömavbrott, och hemberedskap. Den är en
vanlig HTML-fil som går att skriva ut. Lägg gärna broschyren *Om krisen eller kriget
kommer* (Myndigheten för civilt försvar) som PDF i `egna-filer/`.

Startskripten klarar att stickan saknar körrättigheter (exFAT, `noexec`) och
macOS karantänflagga, genom att köra en kopia av kiwix-serve från datorns tempmapp.
På Linux används en installerad `kiwix-serve` (`sudo apt install kiwix-tools`) om
stickans saknas.

## Tester

```
python3 -m unittest discover -s offline-usb/tests -v
```

Testerna kör byggskriptet mot en lokal kopia av en Kiwix-spegel: val av nivå och
språk, nyaste utgåvan, återupptagna och avbrutna nedladdningar, SHA-256, att
gamla utgåvor tas bort och att portalens lista skrivs.

## Ansvar

Ett uppslagsverk, inte en ersättning för 112, vården eller myndigheternas besked.
Innehållet kommer från fria källor och kan vara fel eller inaktuellt. Nödkorten är
korta sammanfattningar av offentliga råd och har inte granskats av sjukvårdspersonal.
