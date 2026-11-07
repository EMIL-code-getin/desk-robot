// Everything you are likely to want to change lives in this file:
// the Bluetooth name, the pins, and what every key does.
#pragma once
#include "actions.h"

// ============================================================================
// Bluetooth
// ============================================================================
// The name shown when you pair. If you change it after pairing, remove the
// device on the computer and pair again.
#define DEVICE_NAME  "Stream Deck"
#define MANUFACTURER "DIY"

// ============================================================================
// Pins
// ============================================================================
// Wire every switch between its pin and GND. The encoder's middle pin (C) goes
// to GND, A and B to the pins below, and the push switch between ENC_SW and
// GND. No resistors or diodes: the chip's internal pull-ups are used.
//
// The board is picked by the PlatformIO environment (platformio.ini). In the
// Arduino IDE it falls back to the chip: ESP32-C3 -> XIAO ESP32C3, ESP32-C6 ->
// XIAO ESP32C6.
#if !defined(BOARD_XIAO_ESP32C3) && !defined(BOARD_XIAO_ESP32C6) && \
    !defined(BOARD_ESP32C6_DEVKITC)
  #include <sdkconfig.h>
  #if defined(CONFIG_IDF_TARGET_ESP32C3)
    #define BOARD_XIAO_ESP32C3
  #else
    #define BOARD_XIAO_ESP32C6
  #endif
#endif

#if defined(BOARD_XIAO_ESP32C3)
// Seeed XIAO ESP32C3. Keys on the left row of pins, encoder on the right row
// next to GND.
//
//   Function   XIAO pin   GPIO
//   Key 1..6   D0..D5     2, 3, 4, 5, 6, 7
//   Encoder A  D8         8
//   Encoder B  D10        10
//   Enc. push  D7         20
//
// Unused on purpose: D9 (GPIO9 = BOOT button; held low at power-on the chip
// starts in download mode) and D6 (GPIO21 = serial TX, free for an LED).
static const uint8_t KEY_PINS[NUM_KEYS] = {2, 3, 4, 5, 6, 7};
#define ENC_A_PIN  8
#define ENC_B_PIN  10
#define ENC_SW_PIN 20

#else
// ESP32-C6 (XIAO ESP32C6 or DevKitC-1; same GPIO numbers on both):
//
//   Function   GPIO   XIAO ESP32C6   DevKitC-1 header
//   Key 1       0       D0             0
//   Key 2       1       D1             1
//   Key 3       2       D2             2
//   Key 4      21       D3            21
//   Key 5      22       D4            22
//   Key 6      23       D5            23
//   Encoder A  19       D8            19
//   Encoder B  20       D9            20
//   Enc. push  18       D10           18
//
// Avoid GPIO 8, 9 and 15 (boot strapping), 12/13 (USB) and 16/17 (serial).
static const uint8_t KEY_PINS[NUM_KEYS] = {0, 1, 2, 21, 22, 23};
#define ENC_A_PIN  19
#define ENC_B_PIN  20
#define ENC_SW_PIN 18
#endif

// If turning right lowers the volume, swap A/B here instead of re-soldering.
#define ENC_REVERSE false

// Most EC11 encoders click once per full electrical cycle (20 detents and
// 20 pulses per turn). If yours needs two clicks per step, set this to true.
// If it jumps two steps per click, set it to false.
#define ENC_HALF_STEP false

// ============================================================================
// Status LED
// ============================================================================
// XIAO ESP32C3: no user LED on the board (only the charge LED), so fit the
//               external LED below if you want to see layers and pairing.
// XIAO ESP32C6: yellow user LED on GPIO15, lit when the pin is LOW.
// DevKitC-1:    RGB LED on GPIO8 (driven as a single-pixel WS2812).
//
// EXTRA_LED_PIN: optional 3 mm LED in the case's top hole (anode to this pin
// through a 330 ohm resistor, cathode to GND). -1 = not fitted.
// Default on the XIAO ESP32C3 is GPIO21 (D6); driving it is harmless if no
// LED is fitted. On the XIAO ESP32C6, D7 (GPIO17) is a good choice.
#if defined(BOARD_ESP32C6_DEVKITC)
  #define STATUS_LED_RGB_PIN 8
#elif defined(BOARD_XIAO_ESP32C6)
  #define STATUS_LED_PIN       15
  #define STATUS_LED_ACTIVE_LOW true
#endif
#if defined(BOARD_XIAO_ESP32C3)
  #define EXTRA_LED_PIN 21
#else
  #define EXTRA_LED_PIN -1
#endif

// ============================================================================
// Timing
// ============================================================================
#define DEBOUNCE_MS        5    // ignore switch bounce shorter than this
#define LAYER_HOLD_MS      600  // hold the knob this long to change layer
#define TAP_MS             12   // how long a "tap" (encoder step, text) is held
#define CLEAR_BONDS_HOLD   true // hold key 1 + knob while powering on to forget
                                // all paired computers

// ============================================================================
// Keymap
// ============================================================================
// Physical layout, seen from above with the USB cable at the back:
//
//        back (USB)
//   +----+----+----+
//   | 1  | 2  | 3  |   ( knob )
//   +----+----+----+
//   | 4  | 5  | 6  |
//   +----+----+----+
//        front
//
// Hold the knob for LAYER_HOLD_MS to step to the next layer; the LED blinks
// once for layer 1, twice for layer 2, and so on. The current layer is saved
// and restored after a power cycle.
//
// Actions:
//   KEY(KEY_F13)                  a single key
//   COMBO(MOD_CTRL, KEY_C)        key with modifiers (MOD_CTRL | MOD_SHIFT ...)
//   MEDIA(MEDIA_VOL_UP)           media key
//   TEXT("hello")                 types text (a-z, A-Z, 0-9, space, ".", ",",
//                                 "\n"; works on Swedish and US layouts)
//   NEXT_LAYER                    switch layer
//   NONE                          does nothing
//
// Keys send "key down" while held and "key up" on release, so push-to-talk
// style bindings work.

static const Layer LAYERS[] = {
  {
    // Layer 1: F13-F18. Nothing on a normal keyboard uses these, so bind them
    // to whatever you like in OBS, Discord, Streamer.bot, AutoHotkey, etc.
    "F-keys",
    {
      KEY(KEY_F13), KEY(KEY_F14), KEY(KEY_F15),
      KEY(KEY_F16), KEY(KEY_F17), KEY(KEY_F18),
    },
    MEDIA(MEDIA_VOL_UP),    // turn right
    MEDIA(MEDIA_VOL_DOWN),  // turn left
    MEDIA(MEDIA_MUTE),      // click
  },
  {
    // Layer 2: media and calls.
    "Media",
    {
      MEDIA(MEDIA_PREV),             MEDIA(MEDIA_PLAY_PAUSE),     MEDIA(MEDIA_NEXT),
      COMBO(MOD_CTRL | MOD_SHIFT, KEY_M),  // mute mic in Teams
      COMBO(MOD_CTRL | MOD_SHIFT, KEY_O),  // camera on/off in Teams
      COMBO(MOD_GUI | MOD_SHIFT, KEY_S),   // Windows: screenshot snip
    },
    MEDIA(MEDIA_VOL_UP),
    MEDIA(MEDIA_VOL_DOWN),
    MEDIA(MEDIA_PLAY_PAUSE),
  },
  {
    // Layer 3: editing. The knob scrubs through undo/redo.
    "Edit",
    {
      COMBO(MOD_CTRL, KEY_C), COMBO(MOD_CTRL, KEY_V), COMBO(MOD_CTRL, KEY_X),
      COMBO(MOD_CTRL, KEY_S), COMBO(MOD_CTRL, KEY_F), COMBO(MOD_GUI, KEY_D),
    },
    COMBO(MOD_CTRL, KEY_Y),  // redo
    COMBO(MOD_CTRL, KEY_Z),  // undo
    KEY(KEY_ENTER),
  },
};
