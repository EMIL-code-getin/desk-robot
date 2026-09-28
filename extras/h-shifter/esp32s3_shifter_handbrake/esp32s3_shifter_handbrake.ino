/*
 * ============================================================
 *  Simracing-handbroms + H-växel - Seeed XIAO ESP32S3
 *  (bygger på handbroms_esp32s3.ino, AV/PÅ-versionen)
 * ============================================================
 *  Handbromsen fungerar EXAKT som förut, så dina bindningar i
 *  Assetto Corsa (Rally) ligger kvar:
 *    Knapp 1  = handbroms (intryckt när spaken är dragen)
 *    Z-axel   = 0 släppt / 1023 dragen
 *
 *  Nytt: en analog tumstyrspak (KY-023 / PS2-modul) som H-växel.
 *    Knapp 2..7 = växel 1..6   (intryckt så länge växeln ligger i)
 *    Knapp 8    = back (R)
 *    Friläge    = ingen växelknapp intryckt
 *
 *        1   3   5
 *        |   |   |
 *        +---N---+     vänster/höger väljer spår (bara i friläge),
 *        |   |   |     upp/ner lägger i växeln.
 *        2   4   6/R   R = nere till höger MED spakens knapp intryckt.
 *
 *  PINOUT (XIAO ESP32S3):
 *    Hall-sensor:  3V3 -> VCC, GND -> GND, D0 (GPIO1) -> OUT
 *    Styrspak:     3V3 -> VCC (+5V-pinnen på modulen), GND -> GND
 *                  D3 (GPIO4) -> VRx
 *                  D4 (GPIO5) -> VRy
 *                  D5 (GPIO6) -> SW
 *    ALLT på 3V3, aldrig 5V - pinnarna tål max 3.3V.
 *
 *  Vid start mäts både handbromsens viloläge och spakens mittläge.
 *  => HA HANDBROMSEN SLÄPPT OCH SPAKEN I MITTEN NÄR DU KOPPLAR IN.
 *
 *  Serial Monitor (115200 baud, valfritt - bara för felsökning):
 *    r = mät om viloläge + spakens mitt nu
 *    v = visa värden
 *    l = live-utskrift på/av
 *
 *  Arduino IDE (Verktyg):
 *    Board: "XIAO_ESP32S3", USB CDC On Boot: Enabled,
 *    USB Mode: "USB-OTG (TinyUSB)"
 *  Bibliotek: Joystick_ESP32S3 (ChrGri, ZIP från GitHub) - headern
 *   heter Joystick_ESP32S2.h.
 * ============================================================
 */

#include <Joystick_ESP32S2.h>

// 8 knappar (handbroms + 6 växlar + back), inga hattar, bara Z-axel.
Joystick_ Joystick(JOYSTICK_DEFAULT_REPORT_ID, JOYSTICK_TYPE_JOYSTICK,
                   8,      // knappar
                   0,      // hattar
                   false,  // X
                   false,  // Y
                   true,   // Z
                   false, false, false,                 // Rx, Ry, Rz
                   false, false, false, false, false);  // Rudder, Throttle, Accelerator, Brake, Steering

// ------------------------------------------------------------ handbroms --

#define SENSOR_PIN 1   // A0 / D0 / GPIO1

// Hur långt (i ADC-steg, 0-4095) värdet måste röra sig från
// viloläget för att räknas som "dragen". Viloläget ligger runt 2500
// och magneten tar det ända ner mot 0, så 800 är ungefär en tredjedel
// av vägen. Sänk om den triggar för sent, höj om den triggar för tidigt.
const int ON_THRESHOLD  = 800;
const int OFF_THRESHOLD = 500;

const float SMOOTHING_ALPHA = 0.3;
const unsigned long LIVE_PRINT_INTERVAL_MS = 250;

float smoothedValue = 0;
int restValue = 0;
bool pulled = false;
bool livePrint = false;
bool helpShown = false;
unsigned long lastLivePrint = 0;

// --------------------------------------------------------------- växel --

#define SHIFTER_X_PIN   4   // D3 / GPIO4
#define SHIFTER_Y_PIN   5   // D4 / GPIO5
#define SHIFTER_SW_PIN  6   // D5 / GPIO6, aktiv låg (intern pull-up)

// Vänd om växlarna hamnar spegelvänt på din modul.
const bool INVERT_X = false;
const bool INVERT_Y = false;

// Avstånd från mittläget i ADC-steg (spaken svänger ca +-2048).
const int COLUMN_THRESHOLD  = 680;   // förbi detta åt sidan = yttre spår
const int ENGAGE_THRESHOLD  = 1320;  // förbi detta upp/ner = i växel
const int RELEASE_THRESHOLD = 880;   // tillbaka innanför = friläge (hysteres)

// false = 5-växlad med R nere till höger, utan knapp.
const bool REVERSE_NEEDS_BUTTON = true;

enum Gear : uint8_t { NEUTRAL, G1, G2, G3, G4, G5, G6, REVERSE };
const char GEAR_NAMES[8] = {'N', '1', '2', '3', '4', '5', '6', 'R'};

// [spår][0 = upp, 1 = ner]
const Gear GATE[3][2] = {
  {G1, G2},
  {G3, G4},
  {G5, G6},
};

float smoothX = 0;
float smoothY = 0;
int centerX = 2048;
int centerY = 2048;
uint8_t column = 1;     // 0 = vänster, 1 = mitten, 2 = höger
Gear gear = NEUTRAL;

// -------------------------------------------------------------- mätning --

void measureRest() {
  long sum = 0, sumX = 0, sumY = 0;
  for (int i = 0; i < 64; i++) {
    sum  += analogRead(SENSOR_PIN);
    sumX += analogRead(SHIFTER_X_PIN);
    sumY += analogRead(SHIFTER_Y_PIN);
    delay(2);
  }
  restValue = sum / 64;
  smoothedValue = restValue;
  centerX = sumX / 64;
  centerY = sumY / 64;
  smoothX = centerX;
  smoothY = centerY;
}

Gear slotGear(uint8_t col, bool down) {
  Gear g = GATE[col][down ? 1 : 0];
  bool buttonHeld = digitalRead(SHIFTER_SW_PIN) == LOW;
  if (g == G6 && (!REVERSE_NEEDS_BUTTON || buttonHeld)) return REVERSE;
  return g;
}

// x/y är avstånd från mitten, positivt y = spaken framåt (övre raden).
Gear updateGear(int x, int y) {
  int dist = abs(y);

  if (gear != NEUTRAL) {
    // Ligg kvar i växeln tills spaken är tillbaka i mittkanalen.
    if (dist < RELEASE_THRESHOLD) return NEUTRAL;
    return gear;
  }

  // I friläge: spåret följer spaken åt sidan.
  if (x < -COLUMN_THRESHOLD) column = 0;
  else if (x > COLUMN_THRESHOLD) column = 2;
  else column = 1;

  if (dist > ENGAGE_THRESHOLD) return slotGear(column, y < 0);
  return NEUTRAL;
}

// ------------------------------------------------------------- serial --

void printValues() {
  Serial.print(F("Sensor: "));
  Serial.print((int)round(smoothedValue));
  Serial.print(F("  | Vilolage: "));
  Serial.print(restValue);
  Serial.print(F("  | Avvikelse: "));
  Serial.print(abs((int)round(smoothedValue) - restValue));
  Serial.print(F(" (pa vid >"));
  Serial.print(ON_THRESHOLD);
  Serial.print(F(")  | Handbroms: "));
  Serial.print(pulled ? F("DRAGEN") : F("slappt"));
  Serial.print(F("  | Spak X/Y: "));
  Serial.print((int)round(smoothX) - centerX);
  Serial.print(F("/"));
  Serial.print(-((int)round(smoothY) - centerY));
  Serial.print(F("  | Vaxel: "));
  Serial.println(GEAR_NAMES[gear]);
}

void printHelp() {
  Serial.println();
  Serial.println(F("=== Handbroms (av/pa) + H-vaxel ==="));
  Serial.println(F(" r = mat om vilolage + spakens mitt nu"));
  Serial.println(F(" v = visa varden"));
  Serial.println(F(" l = live-utskrift pa/av"));
  Serial.println();
}

void handleSerialCommands() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == 'r' || c == 'R') {
      measureRest();
      Serial.print(F("# Nytt vilolage: "));
      Serial.print(restValue);
      Serial.print(F("  | Spakens mitt X/Y: "));
      Serial.print(centerX);
      Serial.print(F("/"));
      Serial.println(centerY);
    } else if (c == 'v' || c == 'V') {
      printValues();
    } else if (c == 'l' || c == 'L') {
      livePrint = !livePrint;
      Serial.println(livePrint ? F("# Live-utskrift PA") : F("# Live-utskrift AV"));
    } else if (c == 'h' || c == 'H' || c == '?') {
      printHelp();
    }
  }
}

// ---------------------------------------------------------------- main --

void setup() {
  Serial.begin(115200);
  pinMode(SHIFTER_SW_PIN, INPUT_PULLUP);
  delay(300);          // låt sensorerna stabilisera sig
  measureRest();
  Joystick.setZAxisRange(0, 1023);
  Joystick.begin(false);
}

void loop() {
  // Handbroms - oförändrad.
  int raw = analogRead(SENSOR_PIN);
  smoothedValue = SMOOTHING_ALPHA * raw + (1.0 - SMOOTHING_ALPHA) * smoothedValue;

  int deviation = abs((int)round(smoothedValue) - restValue);
  if (!pulled && deviation > ON_THRESHOLD)  pulled = true;
  if (pulled  && deviation < OFF_THRESHOLD) pulled = false;

  // Växel. Y-axeln på de flesta moduler visar högre när man drar spaken
  // mot sig, därav minustecknet: positivt = framåt = övre raden i H:et.
  smoothX = SMOOTHING_ALPHA * analogRead(SHIFTER_X_PIN) + (1.0 - SMOOTHING_ALPHA) * smoothX;
  smoothY = SMOOTHING_ALPHA * analogRead(SHIFTER_Y_PIN) + (1.0 - SMOOTHING_ALPHA) * smoothY;
  int x = (int)round(smoothX) - centerX;
  int y = -((int)round(smoothY) - centerY);
  if (INVERT_X) x = -x;
  if (INVERT_Y) y = -y;

  Gear next = updateGear(x, y);
  if (next != gear) {
    gear = next;
    if (Serial) {
      Serial.print(F("# Vaxel: "));
      Serial.println(GEAR_NAMES[gear]);
    }
  }

  Joystick.setButton(0, pulled ? 1 : 0);
  Joystick.setZAxis(pulled ? 1023 : 0);
  // Knapp 2..8 = växel 1..6, R (Gear-värdet 1..7 är precis knappindex).
  for (uint8_t g = G1; g <= REVERSE; g++) {
    Joystick.setButton(g, gear == g ? 1 : 0);
  }
  Joystick.sendState();

  if (Serial) {
    if (!helpShown) {
      delay(200);
      printHelp();
      printValues();
      helpShown = true;
    }
    handleSerialCommands();
    unsigned long now = millis();
    if (livePrint && now - lastLivePrint >= LIVE_PRINT_INTERVAL_MS) {
      lastLivePrint = now;
      printValues();
    }
  } else {
    helpShown = false;
  }

  delay(5);
}
