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

// Without diodes, three held keys in an "L" also pull the fourth corner of
// their rectangle low. A reading where two rows share two or more pressed
// columns may contain such a ghost, so it cannot be trusted.
bool matrixIsAmbiguous(uint16_t mask) {
  const uint16_t rowMask = (1u << MATRIX_COLS) - 1;
  for (uint8_t a = 0; a < MATRIX_ROWS; a++) {
    for (uint8_t b = a + 1; b < MATRIX_ROWS; b++) {
      uint16_t shared = ((mask >> (a * MATRIX_COLS)) & rowMask) &
                        ((mask >> (b * MATRIX_COLS)) & rowMask);
      if (shared & (shared - 1)) return true;  // two or more bits set
    }
  }
  return false;
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

// Which key (and modifiers) produces a character, for the keyboard layout set
// in Windows. Letters, digits and space are the same on both layouts.
struct CharKey {
  char c;
  uint8_t mods;
  uint8_t key;
};

#if KEYBOARD_LAYOUT_SE
const CharKey SPECIAL_CHARS[] = {
  {'.', 0, KEY_DOT},        {':', MOD_SHIFT, KEY_DOT},
  {',', 0, KEY_COMMA},      {';', MOD_SHIFT, KEY_COMMA},
  {'-', 0, KEY_SLASH},      {'_', MOD_SHIFT, KEY_SLASH},
  {'+', 0, KEY_MINUS},      {'?', MOD_SHIFT, KEY_MINUS},
  {'\\', MOD_ALTGR, KEY_MINUS},
  {'!', MOD_SHIFT, KEY_1},  {'"', MOD_SHIFT, KEY_2},  {'@', MOD_ALTGR, KEY_2},
  {'#', MOD_SHIFT, KEY_3},  {'$', MOD_ALTGR, KEY_4},  {'%', MOD_SHIFT, KEY_5},
  {'&', MOD_SHIFT, KEY_6},  {'/', MOD_SHIFT, KEY_7},  {'{', MOD_ALTGR, KEY_7},
  {'(', MOD_SHIFT, KEY_8},  {'[', MOD_ALTGR, KEY_8},  {')', MOD_SHIFT, KEY_9},
  {']', MOD_ALTGR, KEY_9},  {'=', MOD_SHIFT, KEY_0},  {'}', MOD_ALTGR, KEY_0},
  {'\'', 0, KEY_BACKSLASH}, {'*', MOD_SHIFT, KEY_BACKSLASH},
  {'<', 0, KEY_NONUS_BACKSLASH}, {'>', MOD_SHIFT, KEY_NONUS_BACKSLASH},
  {'|', MOD_ALTGR, KEY_NONUS_BACKSLASH},
};
#else
const CharKey SPECIAL_CHARS[] = {
  {'.', 0, KEY_DOT},        {'>', MOD_SHIFT, KEY_DOT},
  {',', 0, KEY_COMMA},      {'<', MOD_SHIFT, KEY_COMMA},
  {'-', 0, KEY_MINUS},      {'_', MOD_SHIFT, KEY_MINUS},
  {'=', 0, KEY_EQUAL},      {'+', MOD_SHIFT, KEY_EQUAL},
  {'/', 0, KEY_SLASH},      {'?', MOD_SHIFT, KEY_SLASH},
  {';', 0, KEY_SEMICOLON},  {':', MOD_SHIFT, KEY_SEMICOLON},
  {'\'', 0, KEY_APOSTROPHE}, {'"', MOD_SHIFT, KEY_APOSTROPHE},
  {'[', 0, KEY_LEFTBRACE},  {'{', MOD_SHIFT, KEY_LEFTBRACE},
  {']', 0, KEY_RIGHTBRACE}, {'}', MOD_SHIFT, KEY_RIGHTBRACE},
  {'\\', 0, KEY_BACKSLASH}, {'|', MOD_SHIFT, KEY_BACKSLASH},
  {'!', MOD_SHIFT, KEY_1},  {'@', MOD_SHIFT, KEY_2},  {'#', MOD_SHIFT, KEY_3},
  {'$', MOD_SHIFT, KEY_4},  {'%', MOD_SHIFT, KEY_5},  {'&', MOD_SHIFT, KEY_7},
  {'*', MOD_SHIFT, KEY_8},  {'(', MOD_SHIFT, KEY_9},  {')', MOD_SHIFT, KEY_0},
};
#endif

bool asciiToKey(char c, uint8_t& mods, uint8_t& key) {
  mods = 0;
  if (c >= 'a' && c <= 'z') { key = KEY_A + (c - 'a'); return true; }
  if (c >= 'A' && c <= 'Z') { key = KEY_A + (c - 'A'); mods = MOD_SHIFT; return true; }
  if (c >= '1' && c <= '9') { key = KEY_1 + (c - '1'); return true; }
  if (c == '0') { key = KEY_0; return true; }
  if (c == ' ') { key = KEY_SPACE; return true; }
  if (c == '\n') { key = KEY_ENTER; return true; }
  if (c == '\t') { key = KEY_TAB; return true; }
  for (const CharKey& ck : SPECIAL_CHARS) {
    if (ck.c == c) {
      mods = ck.mods;
      key = ck.key;
      return true;
    }
  }
  return false;
}

// Press and release one key combination (key may be 0 for modifiers only).
void tapCombo(uint8_t mods, uint8_t key, uint32_t gapMs) {
  Action k = {ACT_KEY, mods, key, nullptr, ""};
  sendKeyboard(&k);
  delay(gapMs);
  sendKeyboard();
  delay(gapMs);
}

void typeText(const char* text) {
  for (const char* p = text; p != nullptr && *p; p++) {
    uint8_t mods, code;
    if (asciiToKey(*p, mods, code)) tapCombo(mods, code, TYPE_MS);
  }
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
      typeText(a.text);
      break;
    case ACT_RUN:
      // Win+R opens the Run box; a web address there opens the default
      // browser, a program or file name starts it.
      tapCombo(MOD_GUI, KEY_R, TYPE_MS);
      delay(RUN_DIALOG_MS);
      typeText(a.text);
      tapCombo(0, KEY_ENTER, TYPE_MS);
      break;
    case ACT_SEARCH:
      // The Windows key opens Start; typing searches, Enter starts the top
      // result. If the program is already open, Windows switches to it.
      tapCombo(MOD_GUI, 0, TYPE_MS);
      delay(SEARCH_OPEN_MS);
      typeText(a.text);
      delay(SEARCH_RESULT_MS);
      tapCombo(0, KEY_ENTER, TYPE_MS);
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

  static uint16_t lastGoodMatrix = 0;
  uint16_t matrix = scanMatrix();
  if (!MATRIX_HAS_DIODES && matrixIsAmbiguous(matrix)) {
    matrix = lastGoodMatrix;  // keep the last trustworthy reading
  } else {
    lastGoodMatrix = matrix;
  }
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
