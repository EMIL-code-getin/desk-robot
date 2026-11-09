# Lär dig Docker från noll

En guide på svenska för dig som aldrig har använt Docker och inte är van
programmerare. Du börjar med att installera, kör sedan färdiga program, och
bygger till sist egna. Varje steg bygger på det förra, så gå igenom dem i
ordning och skriv kommandona själv i stället för att bara läsa.

Räkna med ungefär två till tre timmar för hela guiden. Det går bra att dela
upp den på flera kvällar.

**Innehåll**

1. [Vad är Docker?](#1-vad-är-docker)
2. [Det här behöver du ladda ner](#2-det-här-behöver-du-ladda-ner)
3. [Dina första kommandon](#3-dina-första-kommandon)
4. [Exempel 1: en egen webbsida](#4-exempel-1-en-egen-webbsida)
5. [Exempel 2: ett Python-program](#5-exempel-2-ett-python-program)
6. [Exempel 3: en webbapp med paket](#6-exempel-3-en-webbapp-med-paket)
7. [Exempel 4: två containrar som samarbetar](#7-exempel-4-två-containrar-som-samarbetar)
8. [Det här ska du tänka på](#8-det-här-ska-du-tänka-på)
9. [Fusklapp](#9-fusklapp)
10. [Vanliga fel](#10-vanliga-fel)
11. [Nästa steg](#11-nästa-steg)

Alla exempel ligger färdiga i mappen [`exempel/`](exempel/). De är testkörda
med Docker 29.

---

## 1. Vad är Docker?

Ett program behöver mer än sin egen kod för att fungera. Det behöver rätt
version av Python, rätt paket, rätt inställningar. Därför fungerar ett program
ofta på en dator men inte på en annan.

Docker löser det genom att packa programmet **tillsammans med allt det
behöver** i ett paket. Paketet fungerar likadant på din dator, på en kollegas
dator och på en server.

Det finns fyra ord du behöver kunna. Resten av guiden använder dem hela tiden.

| Ord | Vad det är | Liknelse |
| --- | --- | --- |
| **Image** | Ett färdigt paket med program och allt det behöver. Ändras aldrig. | Ett recept |
| **Container** | En image som körs just nu. Du kan starta många från samma image. | En maträtt lagad efter receptet |
| **Dockerfile** | En textfil med instruktioner för hur en image byggs. | Hur receptet skrivs ner |
| **Docker Hub** | En webbplats med färdiga images som andra har byggt. | En kokbok |

Det viktigaste att förstå: **en container är en slit-och-släng-vara.** Du
startar den, använder den och slänger den. Det du ändrar inuti en container
försvinner när den tas bort. Imagen finns kvar, och från den startar du en ny
container på en sekund. Hur du sparar data som ska finnas kvar kommer i
exempel 4.

---

## 2. Det här behöver du ladda ner

### Docker Desktop

Ladda ner **Docker Desktop** från <https://www.docker.com/products/docker-desktop/>.
Det är ett vanligt program som du installerar genom att klicka dig igenom
installationen.

- **Windows:** Välj standardvalen. Installationen använder något som heter
  WSL 2, och den erbjuder sig att slå på det åt dig. Säg ja. Datorn kan behöva
  startas om.
- **Mac:** Det finns två versioner. Välj *Apple silicon* om din Mac har ett
  M-chip (M1 eller nyare), annars *Intel*. Titta under Apple-menyn, *Om den
  här datorn*, om du är osäker.
- **Linux:** Följ instruktionerna för din distribution på
  <https://docs.docker.com/engine/install/>.

När du startar Docker Desktop första gången frågar det om du vill logga in.
Det behövs inte för den här guiden, du kan hoppa över det.

Docker Desktop är gratis för privat bruk och för mindre företag. Större
företag behöver en betald licens, så kolla villkoren om du ska använda det på
jobbet.

### En textredigerare

Du kommer att öppna och ändra textfiler. [Visual Studio Code](https://code.visualstudio.com/)
är gratis och fungerar bra. Anteckningar i Windows går också.

### Exempelfilerna

Exemplen ligger i det här repot. Har du inte repot på din dator kan du ladda
ner det som zip-fil från GitHub: knappen **Code**, sedan **Download ZIP**.
Packa upp filen någonstans där du hittar den.

### Kontrollera att det fungerar

1. Starta Docker Desktop och vänta tills det står att Docker körs (en liten
   val-ikon syns vid klockan på Windows, i menyraden på Mac).
2. Öppna en terminal. På Windows heter programmet **PowerShell**, på Mac
   **Terminal**.
3. Skriv det här och tryck Enter:

```bash
docker --version
```

Du ska få ett svar i stil med `Docker version 29.x.x`. Får du ett
felmeddelande, se [Vanliga fel](#10-vanliga-fel).

> **Kom ihåg:** Docker Desktop måste vara igång för att kommandona ska
> fungera. Det är det vanligaste felet i början.

---

## 3. Dina första kommandon

Innan du bygger något eget ska du köra images som andra har byggt.

### Hello world

```bash
docker run hello-world
```

Första gången ser du `Unable to find image 'hello-world:latest' locally`.
Det är inget fel. Docker säger bara att imagen inte finns på din dator än och
hämtar den från Docker Hub. Sedan startas en container som skriver ut
`Hello from Docker!` och avslutas.

Du har nu gjort det viktigaste i Docker: **hämtat en image och startat en
container från den.**

### En riktig webbserver

Nu startar du webbservern nginx, utan att installera den på din dator.

```bash
docker run -d -p 8080:80 --name min-server nginx:1.29-alpine
```

Öppna <http://localhost:8080> i webbläsaren. Du ska se "Welcome to nginx!".

Kommandot ser krångligt ut, men varje del har en enkel betydelse:

| Del | Betydelse |
| --- | --- |
| `docker run` | Starta en container |
| `-d` | Kör i bakgrunden så att du får tillbaka terminalen |
| `-p 8080:80` | Koppla port 8080 på din dator till port 80 i containern |
| `--name min-server` | Ge containern ett namn som du själv väljer |
| `nginx:1.29-alpine` | Vilken image som ska användas, och vilken version |

**Portar** är det som brukar vara svårast i början. En container är avstängd
från omvärlden. Med `-p` öppnar du en dörr in till den. Talet till vänster är
din dator, talet till höger är containern: `-p DIN_DATOR:CONTAINERN`.

### Titta, stoppa och städa

Se vilka containrar som körs:

```bash
docker ps
```

Se vad containern har skrivit ut (dess logg):

```bash
docker logs min-server
```

Stoppa den:

```bash
docker stop min-server
```

Containern är stoppad men finns kvar. `docker ps` visar bara de som körs. För
att se alla, även stoppade:

```bash
docker ps -a
```

Ta bort den:

```bash
docker rm min-server
```

Se vilka images som finns på din dator:

```bash
docker images
```

> **Prova själv:** Starta nginx igen, men byt `8080` mot `9000`. Vilken adress
> ska du skriva i webbläsaren nu? Stoppa och ta bort containern när du är klar.

---

## 4. Exempel 1: en egen webbsida

Nu bygger du din första egna image. Den innehåller webbservern nginx plus en
sida som du själv bestämmer över. Du behöver inte kunna programmera för det
här exemplet.

Mappen [`exempel/01-webbsida/`](exempel/01-webbsida/) innehåller två filer:

- `index.html` är webbsidan.
- `Dockerfile` är instruktionerna till Docker.

Så här ser `Dockerfile` ut:

```dockerfile
# Börja från en färdig image som redan innehåller webbservern nginx.
FROM nginx:1.29-alpine

# Kopiera in vår sida dit nginx letar efter sidor att visa.
COPY index.html /usr/share/nginx/html/index.html
```

Bara två instruktioner:

- `FROM` säger vilken image du utgår från. Du bygger nästan aldrig från
  ingenting, utan ovanpå något som redan finns.
- `COPY` kopierar en fil från din dator in i imagen.

Rader som börjar med `#` är kommentarer och påverkar ingenting.

### Bygg och kör

Gå till mappen i terminalen. Sökvägen utgår från repots översta mapp:

```bash
cd docs/docker-guide/exempel/01-webbsida
```

Bygg imagen:

```bash
docker build -t min-webbsida .
```

`-t min-webbsida` ger imagen ett namn. Punkten på slutet är lätt att missa
men viktig: den betyder "använd filerna i mappen jag står i".

Starta en container från din image:

```bash
docker run -d -p 8080:80 --name webbsida min-webbsida
```

Öppna <http://localhost:8080>. Där är din sida.

### Ändra sidan

Öppna `index.html` i textredigeraren, ändra texten i rubriken och spara. Ladda
om sidan i webbläsaren. **Ingenting har hänt.** Det är inget fel, och det är
en av de viktigaste sakerna att förstå med Docker:

> Imagen är en ögonblicksbild. Filen kopierades in när du byggde. Ändrar du
> filen efteråt måste du **bygga om imagen och starta en ny container.**

Gör det i tre steg. Ta bort den gamla containern (`-f` stoppar den först):

```bash
docker rm -f webbsida
```

Bygg om:

```bash
docker build -t min-webbsida .
```

Starta en ny:

```bash
docker run -d -p 8080:80 --name webbsida min-webbsida
```

Ladda om sidan. Nu syns ändringen. Städa när du är klar:

```bash
docker rm -f webbsida
```

> **Prova själv:** Lägg till en rad i `index.html`, till exempel ett stycke med
> dagens datum, och få den att synas i webbläsaren.

---

## 5. Exempel 2: ett Python-program

I det här exemplet kör du ett Python-program utan att ha Python installerat på
din dator. Python finns i imagen.

Mappen [`exempel/02-python-skript/`](exempel/02-python-skript/) innehåller
programmet `hej.py` och en `Dockerfile`:

```dockerfile
# En färdig image med Python installerat. "slim" är en mindre variant.
FROM python:3.13-slim

# Mappen inuti containern som resten av raderna utgår från.
WORKDIR /app

# Kopiera in programmet från din dator till /app i imagen.
COPY hej.py .

# Det som körs när containern startar.
CMD ["python", "hej.py"]
```

Två nya instruktioner:

- `WORKDIR` väljer vilken mapp inuti imagen du arbetar i. Finns den inte så
  skapas den.
- `CMD` är kommandot som körs när en container startar. En image har bara ett
  `CMD`.

### Bygg och kör

Gå till mappen. Står du kvar i `01-webbsida` skriver du:

```bash
cd ../02-python-skript
```

Bygg:

```bash
docker build -t hej-python .
```

Kör:

```bash
docker run --rm hej-python
```

Du ska se:

```
Hej världen!
Jag körs med Python 3.13.x inuti en container.
```

Den här containern gör sitt jobb och avslutas direkt. Därför behövs varken
`-d` eller `-p`. `--rm` betyder "ta bort containern automatiskt när den är
klar", så slipper du städa efteråt.

### Skicka in inställningar

Programmet läser en **miljövariabel** som heter `NAMN`. Miljövariabler är det
vanliga sättet att ge en container inställningar utan att bygga om imagen. Du
sätter dem med `-e`:

```bash
docker run --rm -e NAMN=Rocky hej-python
```

Nu står det `Hej Rocky!`. Samma image, annat beteende.

> **Prova själv:** Öppna `hej.py` och lägg till en rad längst ner, till
> exempel `print("Det här lade jag till själv.")`. Vad behöver du göra för att
> den ska synas när du kör?

---

## 6. Exempel 3: en webbapp med paket

Riktiga program använder paket som andra har skrivit. Här bygger du en liten
webbapp med paketet Flask, och lär dig hur paket installeras i en image.

Mappen [`exempel/03-webbapp/`](exempel/03-webbapp/) innehåller fyra filer:

| Fil | Vad den gör |
| --- | --- |
| `app.py` | Webbappen |
| `requirements.txt` | Lista över paket som appen behöver |
| `Dockerfile` | Instruktionerna till Docker |
| `.dockerignore` | Lista över filer som aldrig ska följa med in i imagen |

`Dockerfile`:

```dockerfile
FROM python:3.13-slim

# Gör att utskrifter syns direkt i "docker logs".
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Steg 1: kopiera bara listan över paket och installera dem.
# Den här delen sparas (cachas) och görs bara om när listan ändras.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Steg 2: kopiera koden. Den ändras ofta, så den ligger sist.
COPY app.py .

# Dokumenterar vilken port appen lyssnar på inuti containern.
EXPOSE 5000

CMD ["python", "app.py"]
```

Nya instruktioner:

- `RUN` kör ett kommando **när imagen byggs**. Här installeras paketen.
  Jämför med `CMD`, som körs **när containern startar**.
- `ENV` sätter en miljövariabel som alltid finns i imagen.
- `EXPOSE` är bara en anteckning om vilken port appen använder. Den öppnar
  ingenting. Det gör du fortfarande med `-p`.

### Varför ordningen spelar roll

Docker bygger imagen rad för rad och sparar resultatet av varje rad. Vid nästa
bygge återanvänds allt fram till den första raden där något har ändrats.

Därför kopieras `requirements.txt` in och installeras **före** koden. Ändrar
du bara `app.py` hoppar Docker över paketinstallationen, och bygget tar en
sekund i stället för en minut. Du ser det själv strax.

### Bygg och kör

```bash
cd ../03-webbapp
```

```bash
docker build -t min-webbapp .
```

Första bygget tar en stund eftersom Flask laddas ner.

```bash
docker run -d -p 8080:5000 --name webbapp min-webbapp
```

Öppna <http://localhost:8080>. Lägg märke till `-p 8080:5000`: appen lyssnar
på port 5000 inuti containern, men du når den på 8080 på din dator.

Titta på loggen:

```bash
docker logs webbapp
```

Varje gång du laddar om sidan kommer en ny rad i loggen. Vill du följa loggen
medan den skrivs lägger du till `-f` (avbryt med Ctrl+C):

```bash
docker logs -f webbapp
```

### Se cachen i arbete

Ändra en text i `app.py`, spara, och bygg om:

```bash
docker build -t min-webbapp .
```

Det går mycket fortare den här gången. I utskriften står det `CACHED` vid
steget som installerar paketen.

Byt ut containern mot en ny:

```bash
docker rm -f webbapp
```

```bash
docker run -d -p 8080:5000 --name webbapp min-webbapp
```

Att stoppa den här containern tar ungefär tio sekunder. Det är normalt.

### Titta in i containern

Du kan öppna en terminal inuti en container som körs. Det är bra när något
inte fungerar och du vill se efter själv:

```bash
docker exec -it webbapp sh
```

Nu står du inne i containern. Skriv `ls` för att se filerna i `/app`. Skriv
`exit` för att gå ut. Containern fortsätter köra.

Städa:

```bash
docker rm -f webbapp
```

> **Prova själv:** Appen läser miljövariabeln `HALSNING`. Starta en container
> som visar en annan rubrik utan att du ändrar i `app.py`. Tips: titta på hur
> du använde `-e` i exempel 2.

---

## 7. Exempel 4: två containrar som samarbetar

Riktiga system består ofta av flera delar, till exempel en webbapp och en
databas. Tumregeln i Docker är **en sak per container**. I stället för att
starta varje container för hand med ett långt kommando beskriver du allihop i
en fil, och startar dem med ett enda kommando. Verktyget heter **Docker
Compose** och följer med Docker Desktop.

Exemplet är en besöksräknare. Webbappen räknar hur många gånger sidan har
visats och sparar talet i databasen Redis.

Mappen [`exempel/04-compose/`](exempel/04-compose/) innehåller samma sorts
filer som förra exemplet, plus `compose.yaml`:

```yaml
services:
  # Tjänst 1: vår egen webbapp, byggd från Dockerfile i den här mappen.
  webb:
    build: .
    ports:
      - "8080:5000"   # din dator:containern
    environment:
      REDIS_HOST: databas
    depends_on:
      - databas

  # Tjänst 2: databasen Redis, en färdig image som vi inte behöver bygga.
  databas:
    image: redis:8-alpine
    volumes:
      - besoksdata:/data   # här sparar Redis sin data

# En namngiven volym. Den ligger kvar även när containrarna tas bort.
volumes:
  besoksdata:
```

Det mesta känner du igen. `ports` är samma sak som `-p`, och `environment`
är samma sak som `-e`. Filen är bara ett sätt att skriva ner det du annars
hade skrivit i terminalen.

> **Viktigt:** I den här sortens fil har indragen betydelse. Använd
> mellanslag, inte tabbar, och håll raderna i linje precis som i exemplet.

Två saker är nya.

**Containrar hittar varandra på namn.** Webbappen ansluter till databasen
genom att använda namnet `databas`, samma namn som tjänsten har i filen.
Docker ordnar ett eget litet nätverk åt dem. Lägg också märke till att
databasen inte har någon `ports`-rad. Den går bara att nå från webbappen,
inte från din dator. Öppna bara de dörrar som behövs.

**Volymer sparar data.** Du minns att allt i en container försvinner när den
tas bort. En **volym** är en lagringsplats som ligger utanför containern.
Här kopplas volymen `besoksdata` till mappen `/data` i databasens container,
där Redis sparar sina filer.

### Starta allt

```bash
cd ../04-compose
```

```bash
docker compose up -d --build
```

`--build` bygger om webbappens image om något har ändrats. Öppna
<http://localhost:8080> och ladda om sidan några gånger. Räknaren går upp.

Se att båda tjänsterna körs:

```bash
docker compose ps
```

Se loggar från båda på en gång:

```bash
docker compose logs
```

### Prova att volymen fungerar

Stoppa och ta bort båda containrarna:

```bash
docker compose down
```

Starta dem igen:

```bash
docker compose up -d
```

Ladda om sidan. **Räknaren fortsätter där den slutade**, trots att
databasens container är helt ny. Talet låg i volymen, inte i containern.

Vill du ta bort även volymen och börja om från noll lägger du till `-v`:

```bash
docker compose down -v
```

> **Var försiktig med `-v`.** Det raderar datan på riktigt. I ett övningsexempel
> spelar det ingen roll, men i ett riktigt projekt kan det vara en hel databas.

> **Prova själv:** Ändra `"8080:5000"` till `"9090:5000"` i `compose.yaml` och
> starta om med `docker compose up -d`. På vilken adress finns sidan nu?

---

## 8. Det här ska du tänka på

Ordnat efter hur ofta det ställer till problem för nybörjare.

### Hemligheter hör inte hemma i en image

Lösenord och API-nycklar ska **aldrig** skrivas i en `Dockerfile` eller
kopieras in i en image. Alla som får tag på imagen kan läsa dem, även om du
tar bort filen i en senare rad. Skicka in dem när containern startar i
stället, med `-e` eller med en fil:

```bash
docker run --env-file .env min-webbapp
```

Lägg också `.env` i `.dockerignore` så att filen inte följer med av misstag,
och i `.gitignore` så att den inte hamnar på GitHub.

### Containrar är till för att slängas

Spara aldrig något viktigt inuti en container. Allt som ska finnas kvar ska
ligga i en volym. Ett bra test: om du tar bort containern och startar en ny,
fungerar allt fortfarande? Då har du gjort rätt.

### Ändringar syns inte förrän du bygger om

Ändrar du en fil som kopieras in med `COPY` måste du bygga om imagen och
starta en ny container. "Jag ändrade men inget hände" beror nästan alltid på
att ett av de två stegen har glömts.

### Skriv ut vilken version du vill ha

Skriv `python:3.13-slim`, inte bara `python`. Utan version får du `latest`,
alltså den senaste för dagen. Då kan samma `Dockerfile` ge ett annat resultat
nästa månad, och plötsligt slutar något fungera utan att du har ändrat något.
Samma sak gäller paketen i `requirements.txt`: skriv `flask==3.1.3`, inte
bara `flask`.

### Använd images du kan lita på

Vem som helst kan lägga upp images på Docker Hub. Håll dig till dem som är
märkta **Docker Official Image** eller **Verified Publisher**. En image är ett
program som körs på din dator, så behandla den som allt annat du laddar ner.

### `localhost` inuti en container är containern själv

Inuti en container betyder `localhost` "den här containern", inte din dator.
Därför ansluter webbappen i exempel 4 till `databas` och inte till
`localhost`. Av samma skäl måste en webbapp lyssna på `0.0.0.0` för att gå
att nå utifrån, se kommentaren i `app.py`.

### Öppna bara de portar som behövs

Varje `-p` är en dörr in. En databas som bara ska användas av din webbapp
behöver ingen.

### Docker tar plats på disken

Images, stoppade containrar och gamla byggen samlas på hög. Se hur mycket
plats som används:

```bash
docker system df
```

Städa bort stoppade containrar, oanvända nätverk och överblivna images:

```bash
docker system prune
```

Kommandot frågar innan det raderar. Läs vad det tänker ta bort. Dina volymer
rör det inte.

### Använd `.dockerignore`

Utan den filen kopierar `COPY . .` in allt i mappen, även sådant som inte ska
med: hemligheter, Git-historik, stora filer. Imagen blir större, bygget
långsammare, och i värsta fall läcker något.

### När du har kommit en bit

Det här behöver du inte tänka på nu, men det är bra att ha hört orden:

- **Kör inte som root.** Programmen i exemplen körs som administratör inuti
  containern. I riktiga projekt lägger man till en vanlig användare med
  instruktionen `USER`.
- **Flasks inbyggda server är bara för övning.** I riktiga projekt används en
  server som gunicorn.
- **Mindre images är bättre.** De går fortare att hämta och innehåller färre
  saker som kan ha säkerhetshål. Varianterna `slim` och `alpine` är till för
  det.

---

## 9. Fusklapp

**Images**

| Kommando | Vad det gör |
| --- | --- |
| `docker build -t NAMN .` | Bygg en image från mappen du står i |
| `docker images` | Visa images på din dator |
| `docker pull NAMN` | Hämta en image utan att starta den |
| `docker rmi NAMN` | Ta bort en image |

**Containrar**

| Kommando | Vad det gör |
| --- | --- |
| `docker run NAMN` | Starta en container |
| `docker run -d` | ...i bakgrunden |
| `docker run -p 8080:80` | ...med en port öppen (din dator:containern) |
| `docker run --name X` | ...med ett eget namn |
| `docker run --rm` | ...som tas bort automatiskt när den är klar |
| `docker run -e NAMN=värde` | ...med en miljövariabel |
| `docker ps` | Visa containrar som körs |
| `docker ps -a` | Visa alla, även stoppade |
| `docker logs X` | Visa vad containern har skrivit ut |
| `docker logs -f X` | Följ loggen medan den skrivs |
| `docker exec -it X sh` | Öppna en terminal inuti containern |
| `docker stop X` | Stoppa |
| `docker rm X` | Ta bort en stoppad container |
| `docker rm -f X` | Stoppa och ta bort i ett steg |

**Compose** (körs i mappen där `compose.yaml` ligger)

| Kommando | Vad det gör |
| --- | --- |
| `docker compose up -d` | Starta allt i bakgrunden |
| `docker compose up -d --build` | Bygg om och starta |
| `docker compose ps` | Visa tjänsterna |
| `docker compose logs` | Visa loggar från alla tjänster |
| `docker compose down` | Stoppa och ta bort containrarna |
| `docker compose down -v` | ...och radera volymerna |

**Städning**

| Kommando | Vad det gör |
| --- | --- |
| `docker system df` | Visa hur mycket plats Docker använder |
| `docker system prune` | Ta bort sådant som inte används |

**Dockerfile**

| Instruktion | Vad den gör |
| --- | --- |
| `FROM` | Vilken image du utgår från |
| `WORKDIR` | Vilken mapp du arbetar i inuti imagen |
| `COPY` | Kopiera filer från din dator in i imagen |
| `RUN` | Kör ett kommando när imagen byggs |
| `ENV` | Sätt en miljövariabel |
| `EXPOSE` | Anteckna vilken port programmet använder |
| `CMD` | Vad som körs när containern startar |

---

## 10. Vanliga fel

**`Cannot connect to the Docker daemon`** eller **`error during connect`**

Docker Desktop är inte igång. Starta programmet och vänta tills det är klart.

**`docker: command not found`** eller **`docker känns inte igen`**

Docker är inte installerat, eller så öppnades terminalen före installationen.
Stäng terminalen och öppna en ny.

**`port is already allocated`**

Något annat använder redan porten, ofta en container som du har glömt att
stoppa. Kör `docker ps` och stoppa den, eller välj en annan port till vänster
om kolonet, till exempel `-p 8081:80`.

**`The container name "/webbsida" is already in use`**

Det finns redan en container med det namnet, kanske en stoppad. Ta bort den
med `docker rm -f webbsida` och försök igen.

**Sidan går inte att öppna i webbläsaren**

Gå igenom listan:

1. Körs containern? Kontrollera med `docker ps`. Syns den inte har den
   kraschat. Kör `docker ps -a` och sedan `docker logs NAMN` för att se varför.
2. Har du med `-p`, och är talen åt rätt håll?
3. Använder du samma port i webbläsaren som till vänster om kolonet?

**`failed to read dockerfile`** eller **`no such file or directory`**

Du står i fel mapp. Skriv `ls` (eller `dir` i Windows) och kontrollera att
`Dockerfile` finns där du står.

**`'docker buildx build' requires 1 argument`**

Du har glömt punkten på slutet av `docker build -t NAMN .`

**Mina ändringar syns inte**

Du behöver bygga om imagen och starta en ny container. Se
[Ändra sidan](#ändra-sidan) i exempel 1.

**Windows: installationen klagar på WSL eller virtualisering**

Öppna PowerShell som administratör, kör `wsl --install` och starta om datorn.
Hjälper inte det kan virtualisering vara avstängd i datorns BIOS. Sök då på
datorns modell tillsammans med "enable virtualization".

---

## 11. Nästa steg

När exemplen känns bekväma finns det några naturliga fortsättningar:

- **Bygg något eget.** Ta ett litet program du redan har, eller skriv ett
  nytt, och gör en `Dockerfile` till det. Man lär sig mest av att köra fast
  och ta sig loss.
- **Byt databas.** Byt ut Redis i exempel 4 mot PostgreSQL. Den officiella
  imagens sida på Docker Hub beskriver vilka miljövariabler den behöver.
- **Läs den officiella guiden.** <https://docs.docker.com/get-started/> går
  vidare med sådant som den här guiden hoppar över.

### Ett övningsprojekt: robotens hjärna

Servern i det här repot ([`server/`](../../server/)) är ett Python-program
med en `requirements.txt`, precis som exempel 3. Att packa den i en container
är ett bra övningsprojekt när du har gjort klart guiden. Det finns ingen
färdig `Dockerfile` för den, men du kan redan allt som behövs för att börja.
Tänk på det här:

- **Porten.** Roboten ansluter till servern på port 8765, så den måste
  öppnas: `-p 8765:8765`.
- **Hemligheterna.** API-nycklarna ligger i `server/.env`. De ska skickas in
  med `--env-file`, inte kopieras in i imagen.
- **Stora nedladdningar.** Taligenkänningen laddar ner en modell första
  gången. Utan en volym laddas den ner på nytt varje gång containern byts ut.
- **Mikrofonen.** Servern kan använda datorns egen mikrofon när roboten inte
  är ansluten. En container kommer inte åt datorns ljud utan vidare, så den
  delen är svår att få med.

Fastnar du är det en bra uppgift att ta hjälp med.
