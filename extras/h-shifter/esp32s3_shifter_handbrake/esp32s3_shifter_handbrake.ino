// H-shifter + handbrake as one USB game controller, for the ESP32-S3.
//
// The ESP32-S3 has native USB, so the PC sees this as a normal gamepad: no
// drivers, no serial bridge. Games map it like any controller.
//
//   Gears 1..6 and R  -> gamepad buttons 1..7 (held while in that gear)
//   Handbrake         -> the Rx axis, plus button 8 once pulled past
//                        HANDBRAKE_BUTTON_PERCENT (for games that only
//                        accept a handbrake button)
//
// The shifter works like the Uno version (see ../README.md):
//
//     1   3   5
//     |   |   |
//     +---N---+        left/right picks the column (only while in neutral),
//     |   |   |        up/down puts it in gear.
//     2   4   6/R      R = bottom-right with the stick button held down.
//
// Arduino IDE board settings (Tools menu):
//   Board: your ESP32-S3 board (e.g. "ESP32S3 Dev Module")
//   USB Mode: "USB-OTG (TinyUSB)"      <- required for the gamepad
//   USB CDC On Boot: "Enabled"         <- keeps Serial for debugging
//
// Wiring (all 3.3V, the ESP32-S3 pins are NOT 5V tolerant):
//   Joystick VCC -> 3V3   GND -> GND
//   VRx -> GPIO4   VRy -> GPIO5   SW -> GPIO6
//   Handbrake sensor signal -> HANDBRAKE_PIN (set it to the pin you use now)
//
// Use ADC1 pins (GPIO1..GPIO10) for anything analog. Avoid GPIO0, 3, 45, 46
// (boot straps), 19/20 (USB) and 26..37 (flash/PSRAM on most modules).

#include <Arduino.h>

#ifndef ARDUINO_USB_MODE
#error This board has no native USB. Use an ESP32-S3 (or S2).
#elif ARDUINO_USB_MODE == 1
#error Set Tools > USB Mode to "USB-OTG (TinyUSB)" and compile again.
#else

#include "USB.h"
#include "USBHIDGamepad.h"

USBHIDGamepad Gamepad;

// ---------------------------------------------------------------- settings --

const uint8_t PIN_X = 4;
const uint8_t PIN_Y = 5;
const uint8_t PIN_BUTTON = 6;       // active low, uses the internal pull-up
const uint8_t HANDBRAKE_PIN = 7;    // <- change to your handbrake's pin

// Flip these if the gears come out mirrored on your module.
const bool INVERT_X = false;
const bool INVERT_Y = false;

// Distances from the calibrated center, in ADC counts (12-bit, ~±2048).
const int COLUMN_THRESHOLD = 680;   // past this left/right = outer column
const int ENGAGE_THRESHOLD = 1320;  // past this up/down = in gear
const int RELEASE_THRESHOLD = 880;  // back inside this = out of gear (hysteresis)

const bool REVERSE_NEEDS_BUTTON = true;

// Handbrake raw ADC readings at rest and fully pulled. Watch the Serial
// Monitor (DEBUG_HANDBRAKE = true) while pulling it to find your numbers.
// If released reads higher than pulled, just swap them: it still works.
const int HANDBRAKE_RELEASED = 300;
const int HANDBRAKE_PULLED = 3800;
const int HANDBRAKE_DEADZONE_PERCENT = 3;   // ignore jitter at rest
const int HANDBRAKE_BUTTON_PERCENT = 50;    // 0 = no handbrake button
const bool DEBUG_HANDBRAKE = false;

const uint8_t SMOOTHING_SHIFT = 2;  // exponential smoothing, 0 = off, 4 = heavy
const unsigned long LOOP_INTERVAL_MS = 2;

// ------------------------------------------------------------------ gears --

enum Gear : uint8_t { NEUTRAL, G1, G2, G3, G4, G5, G6, REVERSE };
const char GEAR_NAMES[8] = {'N', '1', '2', '3', '4', '5', '6', 'R'};
const uint8_t HANDBRAKE_BUTTON = 7;   // 0-based, shows up as button 8

// [column][0 = up, 1 = down]
const Gear GATE[3][2] = {
  {G1, G2},
  {G3, G4},
  {G5, G6},
};

int centerX = 2048;
int centerY = 2048;
long smoothX = 0;
long smoothY = 0;
long smoothBrake = 0;

uint8_t column = 1;     // 0 = left, 1 = middle, 2 = right
Gear gear = NEUTRAL;

// ---------------------------------------------------------------- shifter --

void calibrateCenter() {
  // Leave the stick alone while the board starts: this averages its resting
  // position so a module that doesn't rest at exactly mid-scale still works.
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

int readSmoothed(uint8_t pin, long &smooth) {
  smooth += analogRead(pin) - (smooth >> SMOOTHING_SHIFT);
  return smooth >> SMOOTHING_SHIFT;
}

bool buttonHeld() {
  return digitalRead(PIN_BUTTON) == LOW;
}

Gear slotGear(uint8_t col, bool down) {
  Gear g = GATE[col][down ? 1 : 0];
  if (g == G6 && (!REVERSE_NEEDS_BUTTON || buttonHeld())) return REVERSE;
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

// -------------------------------------------------------------- handbrake --

// 0..1000 (tenths of a percent) from the raw reading.
int handbrakePermille(int raw) {
  long span = (long)HANDBRAKE_PULLED - HANDBRAKE_RELEASED;
  long p = ((long)(raw - HANDBRAKE_RELEASED) * 1000) / span;
  if (p < HANDBRAKE_DEADZONE_PERCENT * 10) p = 0;
  return constrain(p, 0, 1000);
}

// Full axis range for the most resolution: -127 = released, 127 = pulled.
int8_t handbrakeAxis(int permille) {
  return (int8_t)(-127 + (permille * 254L) / 1000);
}

// ------------------------------------------------------------------- main --

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  pinMode(PIN_BUTTON, INPUT_PULLUP);

  Gamepad.begin();
  USB.begin();

  calibrateCenter();
  smoothBrake = (long)analogRead(HANDBRAKE_PIN) << SMOOTHING_SHIFT;

  Serial.printf("Shifter + handbrake ready. Center X=%d Y=%d\n", centerX, centerY);
}

void loop() {
  static unsigned long lastRun = 0;
  static uint32_t lastButtons = 0xFFFFFFFF;
  static int8_t lastBrake = 0;
  static unsigned long lastDebug = 0;

  unsigned long now = millis();
  if (now - lastRun < LOOP_INTERVAL_MS) return;
  lastRun = now;

  // The Y axis on most modules reads higher when pulled toward you, so
  // negate it: positive = pushed away = top row of the H.
  int x = readSmoothed(PIN_X, smoothX) - centerX;
  int y = -(readSmoothed(PIN_Y, smoothY) - centerY);
  if (INVERT_X) x = -x;
  if (INVERT_Y) y = -y;

  Gear next = updateGear(x, y);
  if (next != gear) {
    gear = next;
    Serial.printf("Gear: %c\n", GEAR_NAMES[gear]);
  }

  int brakeRaw = readSmoothed(HANDBRAKE_PIN, smoothBrake);
  int brakePermille = handbrakePermille(brakeRaw);
  int8_t brake = handbrakeAxis(brakePermille);

  uint32_t buttons = 0;
  if (gear != NEUTRAL) buttons |= 1UL << (gear - 1);   // G1 -> bit 0 ... R -> bit 6
  if (HANDBRAKE_BUTTON_PERCENT > 0 && brakePermille >= HANDBRAKE_BUTTON_PERCENT * 10) {
    buttons |= 1UL << HANDBRAKE_BUTTON;
  }

  // Only talk to the PC when something changed.
  if (buttons != lastButtons || brake != lastBrake) {
    Gamepad.send(0, 0, 0, 0, brake, 0, HAT_CENTER, buttons);
    lastButtons = buttons;
    lastBrake = brake;
  }

  if (DEBUG_HANDBRAKE && now - lastDebug > 200) {
    lastDebug = now;
    Serial.printf("handbrake raw=%d  %d.%d%%\n", brakeRaw, brakePermille / 10, brakePermille % 10);
  }
}

#endif  // ARDUINO_USB_MODE
