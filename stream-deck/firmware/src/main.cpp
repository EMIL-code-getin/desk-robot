// Stream deck firmware: 6 keys + EC11 rotary encoder on an ESP32-C6,
// connected to the computer as a Bluetooth keyboard with media keys.
//
// Everything you normally change (pins, keymap, name) is in include/config.h.

#include <Arduino.h>
#include <Preferences.h>

#include "ble_hid.h"
#include "config.h"

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
// Debounced switches
// ============================================================================
struct Button {
  uint8_t pin;
  bool pressed = false;     // debounced state
  bool raw = false;         // last raw reading
  uint32_t rawSince = 0;    // when the raw reading last changed
};

Button keys[NUM_KEYS];
Button knob;

// Returns +1 on press, -1 on release, 0 if nothing changed.
int updateButton(Button& b, uint32_t now) {
  bool raw = digitalRead(b.pin) == LOW;
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
// Status LED
// ============================================================================
// Blinks N times after a layer change (N = layer number), blinks slowly while
// waiting for a computer to connect, and is otherwise off (mono LED) or dimly
// shows the layer colour (RGB LED).
const uint8_t LAYER_COLOURS[][3] = {
  {0, 0, 255}, {0, 255, 0}, {255, 80, 0}, {255, 0, 255}, {0, 255, 255},
};
constexpr uint8_t NUM_COLOURS = sizeof(LAYER_COLOURS) / sizeof(LAYER_COLOURS[0]);

uint8_t blinksLeft = 0;
uint32_t blinkPhaseStart = 0;
bool blinkOn = false;
int ledState = -1;  // -1 unknown, 0 off, 1 dim, 2 bright

void writeLed(int state) {
  if (state == ledState) return;
  ledState = state;
#ifdef STATUS_LED_RGB_PIN
  const uint8_t* c = LAYER_COLOURS[currentLayer % NUM_COLOURS];
  uint8_t div = state == 2 ? 4 : 64;  // bright = 1/4, dim = 1/64 of full
  if (state == 0) rgbLedWrite(STATUS_LED_RGB_PIN, 0, 0, 0);
  else rgbLedWrite(STATUS_LED_RGB_PIN, c[0] / div, c[1] / div, c[2] / div);
#else
  digitalWrite(STATUS_LED_PIN, (state == 2) != STATUS_LED_ACTIVE_LOW);
#endif
#if EXTRA_LED_PIN >= 0
  digitalWrite(EXTRA_LED_PIN, state == 2);
#endif
}

void startBlinks(uint8_t n) {
  blinksLeft = n;
  blinkOn = false;
  blinkPhaseStart = millis() - 1000;  // start the first blink immediately
  ledState = -1;
}

void updateLed(uint32_t now) {
  if (blinksLeft > 0) {
    uint32_t phase = blinkOn ? 150 : 200;
    if (now - blinkPhaseStart >= phase) {
      blinkPhaseStart = now;
      blinkOn = !blinkOn;
      if (!blinkOn) blinksLeft--;
    }
    writeLed(blinkOn ? 2 : 0);
    return;
  }
  if (!BleHid::connected()) {
    writeLed((now % 1500) < 120 ? 2 : 0);  // short flash every 1.5 s
    return;
  }
#ifdef STATUS_LED_RGB_PIN
  writeLed(1);
#else
  writeLed(0);
#endif
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
  startBlinks(currentLayer + 1);
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
  Serial.printf("[deck] key %u down\n", i + 1);
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
  int edge = updateButton(knob, now);
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

void setup() {
  Serial.begin(115200);

  for (uint8_t i = 0; i < NUM_KEYS; i++) {
    keys[i].pin = KEY_PINS[i];
    pinMode(KEY_PINS[i], INPUT_PULLUP);
  }
  knob.pin = ENC_SW_PIN;
  pinMode(ENC_SW_PIN, INPUT_PULLUP);
  pinMode(ENC_A_PIN, INPUT_PULLUP);
  pinMode(ENC_B_PIN, INPUT_PULLUP);

#ifdef STATUS_LED_PIN
  pinMode(STATUS_LED_PIN, OUTPUT);
#endif
#if EXTRA_LED_PIN >= 0
  pinMode(EXTRA_LED_PIN, OUTPUT);
#endif
  writeLed(0);

  delay(20);  // let the pull-ups settle before reading the boot combo
  bool clearBonds = CLEAR_BONDS_HOLD && digitalRead(KEY_PINS[0]) == LOW &&
                    digitalRead(ENC_SW_PIN) == LOW;

  prefs.begin("deck", false);
  currentLayer = prefs.getUChar("layer", 0);
  if (currentLayer >= NUM_LAYERS) currentLayer = 0;

  BleHid::begin(DEVICE_NAME, MANUFACTURER);
  if (clearBonds) {
    BleHid::clearBonds();
    Serial.println("[deck] forgot all paired computers");
    startBlinks(10);
  }

  encPrev = (digitalRead(ENC_A_PIN) << 1) | digitalRead(ENC_B_PIN);
  attachInterrupt(ENC_A_PIN, onEncoderEdge, CHANGE);
  attachInterrupt(ENC_B_PIN, onEncoderEdge, CHANGE);

  // Don't treat buttons that are held during boot as fresh presses.
  uint32_t now = millis();
  auto syncToPin = [now](Button& b) {
    b.raw = b.pressed = digitalRead(b.pin) == LOW;
    b.rawSince = now;
  };
  for (Button& b : keys) syncToPin(b);
  syncToPin(knob);
  knobLongFired = knob.pressed;  // swallow the release of the boot combo

  Serial.printf("[deck] ready, layer %u: %s\n", currentLayer + 1,
                LAYERS[currentLayer].name);
}

void loop() {
  uint32_t now = millis();

  for (uint8_t i = 0; i < NUM_KEYS; i++) {
    int edge = updateButton(keys[i], now);
    if (edge > 0) onKeyPressed(i);
    else if (edge < 0) onKeyReleased(i);
  }

  handleKnob(now);

  int16_t steps = takeEncoderSteps();
  const Layer& layer = LAYERS[currentLayer];
  while (steps > 0) { tap(layer.turnRight); steps--; }
  while (steps < 0) { tap(layer.turnLeft); steps++; }

  updateLed(now);
  delay(1);
}
