// HandbrakeShifter.ino – ESP32-S3: analog handbroms + magnetisk sequential-växelspak
// Windows ser EN spelkontroll: X-axel = handbroms, knapp 1 = UPP, knapp 2 = NER.
// Arduino IDE: Board "ESP32S3 Dev Module", USB Mode "USB-OTG (TinyUSB)",
// USB CDC On Boot "Enabled". Bibliotek: "Joystick_ESP32S2" (schnoog).
// Datorn ansluts till kortets NATIVE USB-port (märkt "USB"/"OTG"), inte "UART"/"COM".

#include <Arduino.h>

#if !defined(ARDUINO_USB_MODE)
  #error "Kortet saknar native USB. Använd ett ESP32-S3-kort."
#elif ARDUINO_USB_MODE == 1
  #error "Välj Tools > USB Mode = 'USB-OTG (TinyUSB)'."
#endif

#include <Joystick_ESP32S2.h>

// ---------- Inställningar ----------
const uint8_t PIN_HANDBRAKE  = 1;   // ADC1-pinne (GPIO1-10). Byt till din handbromspinne.
const uint8_t PIN_SHIFT_UP   = 17;  // brytare UPP: NO -> GPIO17, COM -> GND
const uint8_t PIN_SHIFT_DOWN = 18;  // brytare NER: NO -> GPIO18, COM -> GND

const uint8_t HID_BTN_SHIFT_UP   = 0;   // syns som "Knapp 1" i Windows
const uint8_t HID_BTN_SHIFT_DOWN = 1;   // syns som "Knapp 2"

const uint32_t DEBOUNCE_MS  = 5;    // kontakten måste vara stabil så här länge
const uint32_t MIN_PRESS_MS = 50;   // varje växling rapporteras minst så här länge

// Handbroms: råvärden 0..4095. Mät med DEBUG_SERIAL 1 och skriv in dina värden.
const int32_t HB_RAW_REST   = 200;   // släppt handbroms
const int32_t HB_RAW_FULL   = 3800;  // fullt dragen
const int32_t HB_AXIS_MAX   = 4095;
const int32_t HB_HYSTERESIS = 3;     // ignorera brus mindre än så här

#define DEBUG_SERIAL 0   // 1 = skriv värden till Serial Monitor (kalibrering)

const uint32_t AXIS_PERIOD_MS = 2;   // läs handbromsen var 2:a ms
const uint32_t REFRESH_MS     = 20;  // skicka hela läget minst var 20:e ms

// ---------- HID-enhet (måste vara global) ----------
Joystick_ Joystick(
  JOYSTICK_DEFAULT_REPORT_ID, JOYSTICK_TYPE_JOYSTICK,
  2, 0,                       // 2 knappar, 0 hattar
  true, false, false,         // X (handbroms), Y, Z
  false, false, false,        // Rx, Ry, Rz
  false, false,               // roder, gas
  false, false, false);       // accelerator, broms, ratt

// Används bara för att fråga om förra rapporten har skickats,
// eftersom Joystick.sendState() tappar en rapport om USB är upptagen.
USBHID usbHid;

// ---------- Växelbrytare ----------
struct ShiftButton {
  uint8_t  pin, hidButton;
  bool     rawPressed;       // senaste råavläsning
  uint32_t rawChangedAt;     // när råvärdet senast ändrades
  bool     stablePressed;    // avstudsat läge
  bool     holdActive;       // minsta-tryck-timern går
  uint32_t pressStartedAt;
  bool     reported;         // läget som ligger i HID-rapporten
};

ShiftButton shiftUp, shiftDown;

void initButton(ShiftButton &b, uint8_t pin, uint8_t hidButton) {
  b.pin = pin;
  b.hidButton = hidButton;
  pinMode(pin, INPUT_PULLUP);          // öppen = HIGH, sluten = LOW
  b.rawPressed = false;
  b.rawChangedAt = millis();
  b.stablePressed = false;
  b.holdActive = false;
  b.pressStartedAt = 0;
  b.reported = false;
}

// Returnerar true om knappens läge i HID-rapporten ändrades.
bool updateButton(ShiftButton &b, uint32_t now) {
  const bool raw = (digitalRead(b.pin) == LOW);
  if (raw != b.rawPressed) {           // studs eller brus: starta om timern
    b.rawPressed = raw;
    b.rawChangedAt = now;
  }
  if (b.stablePressed != b.rawPressed && (now - b.rawChangedAt) >= DEBOUNCE_MS) {
    b.stablePressed = b.rawPressed;
    if (b.stablePressed) {             // ny växling
      b.holdActive = true;
      b.pressStartedAt = now;
    }
  }
  if (b.holdActive && (now - b.pressStartedAt) >= MIN_PRESS_MS) {
    b.holdActive = false;
  }
  const bool out = b.stablePressed || b.holdActive;
  if (out != b.reported) {
    b.reported = out;
    Joystick.setButton(b.hidButton, out ? 1 : 0);
    return true;
  }
  return false;
}

// ---------- Handbroms (platshållare: analog sensor) ----------
int32_t hbRaw = 0;
int32_t hbAxis = -1;                   // -1 tvingar första uppdateringen

int32_t readHandbrakeRaw() {
  uint32_t sum = 0;
  for (int i = 0; i < 16; i++) sum += analogRead(PIN_HANDBRAKE);   // 16x medelvärde
  return (int32_t)(sum / 16);
}

bool updateHandbrake() {
  hbRaw = readHandbrakeRaw();
  int32_t v = (int32_t)map(hbRaw, HB_RAW_REST, HB_RAW_FULL, 0, HB_AXIS_MAX);
  v = constrain(v, 0, HB_AXIS_MAX);
  const bool atEnd = (v == 0 || v == HB_AXIS_MAX) && v != hbAxis;
  if (hbAxis < 0 || abs(v - hbAxis) > HB_HYSTERESIS || atEnd) {
    hbAxis = v;
    Joystick.setXAxis(v);
    return true;
  }
  return false;
}
// Har du lastcell + HX711: läs bara när data finns, t.ex.
//   if (scale.is_ready()) { hbRaw = scale.read(); ... }  – aldrig blockerande.

// ---------- setup / loop ----------
void setup() {
#if DEBUG_SERIAL
  Serial.begin(115200);
#endif
  initButton(shiftUp, PIN_SHIFT_UP, HID_BTN_SHIFT_UP);
  initButton(shiftDown, PIN_SHIFT_DOWN, HID_BTN_SHIFT_DOWN);

  analogReadResolution(12);
  analogSetPinAttenuation(PIN_HANDBRAKE, ADC_11db);   // ca 0..3,1 V

  Joystick.setXAxisRange(0, HB_AXIS_MAX);
  Joystick.begin(false);   // false = vi skickar själva i loop()
  USB.begin();             // gör inget om USB redan startat vid boot
}

void loop() {
  const uint32_t now = millis();
  static uint32_t lastAxisAt = 0, lastSendAt = 0;
  static bool pending = true;

  bool changed = updateButton(shiftUp, now);
  changed |= updateButton(shiftDown, now);

  if (now - lastAxisAt >= AXIS_PERIOD_MS) {
    lastAxisAt = now;
    changed |= updateHandbrake();
  }
  if (changed || (now - lastSendAt) >= REFRESH_MS) pending = true;

  // Skicka bara när förra rapporten har gått iväg, så att ingen växling tappas.
  if (pending && usbHid.ready()) {
    Joystick.sendState();
    pending = false;
    lastSendAt = now;
  }

#if DEBUG_SERIAL
  static uint32_t lastPrintAt = 0;
  if (now - lastPrintAt >= 200) {
    lastPrintAt = now;
    Serial.printf("raw=%ld axel=%ld upp=%d ner=%d\n", (long)hbRaw, (long)hbAxis,
                  shiftUp.reported ? 1 : 0, shiftDown.reported ? 1 : 0);
  }
#endif
  delay(1);                // ca 1 kHz loop
}
