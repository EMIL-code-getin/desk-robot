// H-shifter from a 2-axis analog joystick, for the Arduino Uno.
//
// The stick is read like a real H-pattern gearbox:
//
//     1   3   5
//     |   |   |
//     +---N---+        left/right picks the column (only while in neutral),
//     |   |   |        up/down puts it in gear.
//     2   4   6/R
//
// Reverse is the bottom-right slot with the stick's push button held down
// (like pushing a real lever down to get past the reverse lockout). Set
// REVERSE_NEEDS_BUTTON to false for a 5-speed with R in the bottom-right.
//
// Wiring (typical KY-023 / PS2-style joystick module):
//   VCC -> 5V     GND -> GND
//   VRx -> A0     VRy -> A1     SW -> D2
//
// Output: the current gear is printed on Serial (115200 baud) every time it
// changes, as "N", "1".."6" or "R". The built-in LED (D13) is lit in any gear
// and off in neutral. Optional: one LED per gear on D3..D9 (see GEAR_LED_PINS).

// ---------------------------------------------------------------- settings --

const uint8_t PIN_X = A0;
const uint8_t PIN_Y = A1;
const uint8_t PIN_BUTTON = 2;   // active low, uses the internal pull-up

// Flip these if the gears come out mirrored on your module.
const bool INVERT_X = false;
const bool INVERT_Y = false;

// Distances from the calibrated center, in ADC counts (full swing is ~±512).
const int COLUMN_THRESHOLD = 170;   // past this left/right = left or right column
const int ENGAGE_THRESHOLD = 330;   // past this up/down = in gear
const int RELEASE_THRESHOLD = 220;  // back inside this = out of gear (hysteresis)

const bool REVERSE_NEEDS_BUTTON = true;

// Set to true to send only the gear number/letter with no extra text, handy
// when another program reads the serial port.
const bool PLAIN_OUTPUT = false;

// Optional per-gear LEDs, in order N, 1, 2, 3, 4, 5, 6, R. Use 0 for "none".
const uint8_t GEAR_LED_PINS[8] = {0, 0, 0, 0, 0, 0, 0, 0};

const uint8_t SMOOTHING_SHIFT = 2;  // exponential smoothing, 0 = off, 4 = heavy
const unsigned long LOOP_INTERVAL_MS = 5;

// ------------------------------------------------------------------ gears --

enum Gear : uint8_t { NEUTRAL, G1, G2, G3, G4, G5, G6, REVERSE };
const char GEAR_NAMES[8] = {'N', '1', '2', '3', '4', '5', '6', 'R'};

// [column][0 = up, 1 = down]
const Gear GATE[3][2] = {
  {G1, G2},
  {G3, G4},
  {G5, G6},
};

int centerX = 512;
int centerY = 512;
long smoothX = 0;
long smoothY = 0;

uint8_t column = 1;     // 0 = left, 1 = middle, 2 = right
Gear gear = NEUTRAL;

// ---------------------------------------------------------------- helpers --

void calibrateCenter() {
  // Leave the stick alone while the board starts: this averages its resting
  // position so a module that doesn't rest at exactly 512 still works.
  long sumX = 0;
  long sumY = 0;
  const int samples = 64;
  for (int i = 0; i < samples; i++) {
    sumX += analogRead(PIN_X);
    sumY += analogRead(PIN_Y);
    delay(2);
  }
  centerX = sumX / samples;
  centerY = sumY / samples;
  smoothX = (long)centerX << SMOOTHING_SHIFT;
  smoothY = (long)centerY << SMOOTHING_SHIFT;
}

int readAxis(uint8_t pin, long &smooth, int center, bool invert) {
  smooth += analogRead(pin) - (smooth >> SMOOTHING_SHIFT);
  int offset = (int)(smooth >> SMOOTHING_SHIFT) - center;
  return invert ? -offset : offset;
}

bool buttonHeld() {
  return digitalRead(PIN_BUTTON) == LOW;
}

Gear slotGear(uint8_t col, bool down) {
  Gear g = GATE[col][down ? 1 : 0];
  if (g == G6 && REVERSE_NEEDS_BUTTON && buttonHeld()) return REVERSE;
  if (g == G6 && !REVERSE_NEEDS_BUTTON) return REVERSE;
  return g;
}

Gear updateGear(int x, int y) {
  // Positive y = stick pushed up (toward the top row of the H).
  int dist = abs(y);

  if (gear != NEUTRAL) {
    // Stay in gear until the stick comes back to the neutral channel.
    if (dist < RELEASE_THRESHOLD) return NEUTRAL;
    return gear;
  }

  // In neutral: the column follows the stick left/right.
  if (x < -COLUMN_THRESHOLD) column = 0;
  else if (x > COLUMN_THRESHOLD) column = 2;
  else column = 1;

  if (dist > ENGAGE_THRESHOLD) return slotGear(column, y < 0);
  return NEUTRAL;
}

void showGear(Gear g) {
  digitalWrite(LED_BUILTIN, g == NEUTRAL ? LOW : HIGH);
  for (uint8_t i = 0; i < 8; i++) {
    if (GEAR_LED_PINS[i]) digitalWrite(GEAR_LED_PINS[i], i == g ? HIGH : LOW);
  }

  if (PLAIN_OUTPUT) {
    Serial.println(GEAR_NAMES[g]);
  } else if (g == NEUTRAL) {
    Serial.println(F("Gear: N"));
  } else {
    Serial.print(F("Gear: "));
    Serial.println(GEAR_NAMES[g]);
  }
}

// ------------------------------------------------------------------- main --

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  pinMode(LED_BUILTIN, OUTPUT);
  for (uint8_t i = 0; i < 8; i++) {
    if (GEAR_LED_PINS[i]) pinMode(GEAR_LED_PINS[i], OUTPUT);
  }

  calibrateCenter();
  if (!PLAIN_OUTPUT) {
    Serial.print(F("H-shifter ready. Center X="));
    Serial.print(centerX);
    Serial.print(F(" Y="));
    Serial.println(centerY);
  }
  showGear(gear);
}

void loop() {
  static unsigned long lastRun = 0;
  unsigned long now = millis();
  if (now - lastRun < LOOP_INTERVAL_MS) return;
  lastRun = now;

  // The Y axis on most modules reads higher when pulled toward you, so
  // negate it: positive = pushed away = top row of the H.
  int x = readAxis(PIN_X, smoothX, centerX, INVERT_X);
  int y = -readAxis(PIN_Y, smoothY, centerY, INVERT_Y);

  Gear next = updateGear(x, y);
  if (next != gear) {
    gear = next;
    showGear(gear);
  }
}
