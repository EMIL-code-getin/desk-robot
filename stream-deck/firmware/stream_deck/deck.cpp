// Stream deck firmware: 9 keys (3x3 matrix) + EC11 rotary encoder + 0.96"
// OLED on a Seeed XIAO ESP32C3, connected to the computer as a Bluetooth
// keyboard with media keys. stream_deck.ino calls deck::setup()/deck::loop().
//
// Everything you normally change (pins, keymap, name) is in config.h.

#include "deck.h"

#include <Arduino.h>
#include <Preferences.h>

#include "ble_hid.h"
#include "config.h"
#include "display.h"

namespace {

constexpr uint8_t NUM_LAYERS = sizeof(LAYERS) / sizeof(LAYERS[0]);

Preferences prefs;
uint8_t currentLayer = 0;

// ============================================================================
// Rotary encoder (interrupt driven, so fast spins are not missed)
// ============================================================================
// Quadrature transition table indexed by (previous AB << 2) | current AB:
// +1 / -1 for a valid step in either direction, 0 for no change or a bounce.
const int8_t QDEC[16] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};

volatile uint8_t encPrev = 0;
volatile int8_t encAcc = 0;
volatile int16_t encSteps = 0;
portMUX_TYPE encMux = portMUX_INITIALIZER_UNLOCKED;

void IRAM_ATTR onEncoderEdge() {
  uint8_t cur = (digitalRead(ENC_A_PIN) << 1) | digitalRead(ENC_B_PIN);
  portENTER_CRITICAL_ISR(&encMux);
  encAcc += QDEC[(encPrev << 2) | cur];
  encPrev = cur;
  // Only count a step when the encoder is back in a detent (both pins high
  // with pull-ups; also both low for half-step encoders). Bounce in between
  // adds and removes counts that cancel out.
  bool detent = (cur == 0b11) || (ENC_HALF_STEP && cur == 0b00);
  if (detent) {
    if (encAcc >= 2) encSteps++;
    else if (encAcc <= -2) encSteps--;
    encAcc = 0;
  }
  portEXIT_CRITICAL_ISR(&encMux);
}

int16_t takeEncoderSteps() {
  portENTER_CRITICAL(&encMux);
  int16_t s = encSteps;
  encSteps = 0;
  portEXIT_CRITICAL(&encMux);
  return ENC_REVERSE ? -s : s;
}

// ============================================================================
// Key matrix
// ============================================================================
// Columns are inputs with pull-ups. Each row in turn is driven LOW while the
// others float, and a pressed key pulls its column LOW. Returns bit i set for
// key i+1 (row by row, starting at the row nearest the display).
uint16_t scanMatrix() {
  uint16_t mask = 0;
  for (uint8_t r = 0; r < MATRIX_ROWS; r++) {
    pinMode(ROW_PINS[r], OUTPUT);
    digitalWrite(ROW_PINS[r], LOW);
    delayMicroseconds(10);  // let the column lines settle
    for (uint8_t c = 0; c < MATRIX_COLS; c++) {
      if (digitalRead(COL_PINS[c]) == LOW) mask |= 1u << (r * MATRIX_COLS + c);
    }
    pinMode(ROW_PINS[r], INPUT);  // float again
  }
  return mask;
}

// ============================================================================
// Debouncing
// ============================================================================
struct Button {
  bool pressed = false;     // debounced state
  bool raw = false;         // last raw reading
  uint32_t rawSince = 0;    // when the raw reading last changed
};

Button keys[NUM_KEYS];
Button knob;

// Returns +1 on press, -1 on release, 0 if nothing changed.
int updateButton(Button& b, bool raw, uint32_t now) {
  if (raw != b.raw) {
    b.raw = raw;
    b.rawSince = now;
  }
  if (b.pressed != b.raw && now - b.rawSince >= DEBOUNCE_MS) {
    b.pressed = b.raw;
    return b.pressed ? 1 : -1;
  }
  return 0;
}

// ============================================================================
// Sending actions
// ============================================================================
// What each physical key is currently holding down. Stored at press time so
// a key always releases what it pressed, even if the layer changed meanwhile.
const Action* held[NUM_KEYS] = {};

void sendKeyboard(const Action* extra = nullptr) {
  uint8_t mods = 0;
  uint8_t codes[6] = {0};
  uint8_t n = 0;
  auto add = [&](const Action* a) {
    if (a == nullptr || a->type != ACT_KEY) return;
    mods |= a->mods;
    if (a->code == 0 || n >= 6) return;
    for (uint8_t i = 0; i < n; i++)
      if (codes[i] == a->code) return;
    codes[n++] = uint8_t(a->code);
  };
  for (const Action* a : held) add(a);
  add(extra);
  BleHid::sendKeys(mods, codes);
}

uint16_t heldMedia() {
  for (const Action* a : held)
    if (a != nullptr && a->type == ACT_MEDIA) return a->code;
  return 0;
}

bool asciiToKey(char c, uint8_t& mods, uint8_t& key) {
  mods = 0;
  if (c >= 'a' && c <= 'z') key = KEY_A + (c - 'a');
  else if (c >= 'A' && c <= 'Z') { key = KEY_A + (c - 'A'); mods = MOD_SHIFT; }
  else if (c >= '1' && c <= '9') key = KEY_1 + (c - '1');
  else if (c == '0') key = KEY_0;
  else if (c == ' ') key = KEY_SPACE;
  else if (c == '\n') key = KEY_ENTER;
  else if (c == '\t') key = KEY_TAB;
  else if (c == '.') key = KEY_DOT;
  else if (c == ',') key = KEY_COMMA;
  else return false;
  return true;
}

void nextLayer() {
  currentLayer = (currentLayer + 1) % NUM_LAYERS;
  prefs.putUChar("layer", currentLayer);
  Serial.printf("[deck] layer %u: %s\n", currentLayer + 1, LAYERS[currentLayer].name);
  Display::layerBanner(LAYERS[currentLayer], currentLayer, NUM_LAYERS);
}

// Press and release an action once (encoder steps, knob click, text).
void tap(const Action& a) {
  switch (a.type) {
    case ACT_KEY:
      sendKeyboard(&a);
      delay(TAP_MS);
      sendKeyboard();
      break;
    case ACT_MEDIA:
      BleHid::sendMedia(a.code);
      delay(TAP_MS);
      BleHid::sendMedia(heldMedia());
      break;
    case ACT_TEXT:
      for (const char* p = a.text; p != nullptr && *p; p++) {
        Action k = NONE;
        uint8_t mods, code;
        if (!asciiToKey(*p, mods, code)) continue;
        k.type = ACT_KEY;
        k.mods = mods;
        k.code = code;
        sendKeyboard(&k);
        delay(TAP_MS);
        sendKeyboard();
        delay(TAP_MS);
      }
      break;
    case ACT_LAYER:
      nextLayer();
      break;
    case ACT_NONE:
      break;
  }
}

void onKeyPressed(uint8_t i) {
  const Action& a = LAYERS[currentLayer].keys[i];
  Serial.printf("[deck] key %u down (%s)\n", i + 1, a.label);
  switch (a.type) {
    case ACT_KEY:
      held[i] = &a;
      sendKeyboard();
      break;
    case ACT_MEDIA:
      held[i] = &a;
      BleHid::sendMedia(a.code);
      break;
    default:
      tap(a);
      break;
  }
}

void onKeyReleased(uint8_t i) {
  const Action* a = held[i];
  held[i] = nullptr;
  if (a == nullptr) return;
  if (a->type == ACT_KEY) sendKeyboard();
  else if (a->type == ACT_MEDIA) BleHid::sendMedia(heldMedia());
}

// Knob push: short click = layer action, long hold = next layer.
uint32_t knobDownAt = 0;
bool knobLongFired = false;

void handleKnob(uint32_t now) {
  int edge = updateButton(knob, digitalRead(ENC_SW_PIN) == LOW, now);
  if (edge != 0) Display::activity();
  if (edge > 0) {
    knobDownAt = now;
    knobLongFired = false;
  } else if (edge < 0 && !knobLongFired) {
    tap(LAYERS[currentLayer].encoderClick);
  }
  if (knob.pressed && !knobLongFired && now - knobDownAt >= LAYER_HOLD_MS) {
    knobLongFired = true;
    nextLayer();
  }
}

}  // namespace

namespace deck {

void setup() {
  // The log goes over the USB-C port ("USB CDC On Boot: Enabled"). Without
  // it, Serial would be the hardware UART on GPIO20/21, which are matrix rows
  // here, so leave the UART alone in that case.
#if ARDUINO_USB_CDC_ON_BOOT
  Serial.begin(115200);
#endif

  for (uint8_t r = 0; r < MATRIX_ROWS; r++) pinMode(ROW_PINS[r], INPUT);
  for (uint8_t c = 0; c < MATRIX_COLS; c++) pinMode(COL_PINS[c], INPUT_PULLUP);
  pinMode(ENC_SW_PIN, INPUT_PULLUP);
  pinMode(ENC_A_PIN, INPUT_PULLUP);
  pinMode(ENC_B_PIN, INPUT_PULLUP);

  Display::begin();
  Display::message(DEVICE_NAME, "Startar...", 800);

  delay(20);  // let the pull-ups settle before reading the boot combo
  uint16_t bootKeys = scanMatrix();
  bool knobAtBoot = digitalRead(ENC_SW_PIN) == LOW;
  bool clearBonds = CLEAR_BONDS_HOLD && (bootKeys & 1u) && knobAtBoot;

  prefs.begin("deck", false);
  currentLayer = prefs.getUChar("layer", 0);
  if (currentLayer >= NUM_LAYERS) currentLayer = 0;

  BleHid::begin(DEVICE_NAME, MANUFACTURER);
  if (clearBonds) {
    BleHid::clearBonds();
    Serial.println("[deck] forgot all paired computers");
    Display::message("Parkopplingar", "raderade", 2500);
  }

  encPrev = (digitalRead(ENC_A_PIN) << 1) | digitalRead(ENC_B_PIN);
  attachInterrupt(ENC_A_PIN, onEncoderEdge, CHANGE);
  attachInterrupt(ENC_B_PIN, onEncoderEdge, CHANGE);

  // Don't treat buttons that are held during boot as fresh presses.
  uint32_t now = millis();
  for (uint8_t i = 0; i < NUM_KEYS; i++) {
    keys[i].raw = keys[i].pressed = bootKeys & (1u << i);
    keys[i].rawSince = now;
  }
  knob.raw = knob.pressed = knobAtBoot;
  knob.rawSince = now;
  knobLongFired = knob.pressed;  // swallow the release of the boot combo

  Serial.printf("[deck] ready, layer %u: %s\n", currentLayer + 1,
                LAYERS[currentLayer].name);
}

void loop() {
  uint32_t now = millis();

  uint16_t matrix = scanMatrix();
  uint16_t pressedMask = 0;
  for (uint8_t i = 0; i < NUM_KEYS; i++) {
    int edge = updateButton(keys[i], matrix & (1u << i), now);
    if (edge != 0) Display::activity();
    if (edge > 0) onKeyPressed(i);
    else if (edge < 0) onKeyReleased(i);
    if (keys[i].pressed) pressedMask |= 1u << i;
  }

  handleKnob(now);

  int16_t steps = takeEncoderSteps();
  if (steps != 0) Display::activity();
  const Layer& layer = LAYERS[currentLayer];
  while (steps > 0) { tap(layer.turnRight); steps--; }
  while (steps < 0) { tap(layer.turnLeft); steps++; }

  Display::State state{currentLayer, NUM_LAYERS, BleHid::connected(),
                       pressedMask, knob.pressed};
  Display::update(LAYERS[currentLayer], state);

  delay(1);
}

}  // namespace deck
