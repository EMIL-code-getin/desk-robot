// Everything you are likely to want to change lives in this file:
// the Bluetooth name, the pins, the display and what every key does.
//
// Hardware: Seeed XIAO ESP32C3, 9 MX switches wired as a 3x3 matrix, an EC11
// rotary encoder module (pins CLK, DT, SW, +, GND), and a 0.96" 128x64 SSD1306 I2C OLED
// (e.g. the one in the SunFounder Ultimate Sensor Kit), built into the
// "Macropad" case from MakerWorld.
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
// Pins (XIAO ESP32C3 has 11 GPIOs; this uses all of them)
// ============================================================================
//   Function        XIAO pin   GPIO
//   Matrix row 1    D10        10     keys 1 2 3  (row nearest the display)
//   Matrix row 2    D7         20     keys 4 5 6
//   Matrix row 3    D6         21     keys 7 8 9
//   Matrix col 1    D0         2      keys 1 4 7  (left)
//   Matrix col 2    D8         8      keys 2 5 8
//   Matrix col 3    D9         9      keys 3 6 9  (right)
//   Encoder CLK     D1         3
//   Encoder DT      D2         4
//   Encoder SW      D3         5      (push)
//   Encoder +       3V3               not 5V: the module pulls CLK/DT up to +
//   Encoder GND     GND
//   OLED SDA        D4         6
//   OLED SCL        D5         7
//
// Each switch connects its column wire directly to its row wire.
//
// Without diodes, holding three keys that form an "L" makes the fourth corner
// of that rectangle look pressed too ("ghosting"). The firmware detects that
// pattern and ignores the new key until one is released, so a phantom key is
// never sent. If you later add diodes (1N4148, black band towards the row),
// set MATRIX_HAS_DIODES to true and any combination of keys works.
#define MATRIX_HAS_DIODES false
//
// GPIO 2, 8 and 9 are boot strapping pins. Rows are not driven during boot and
// the columns have pull-ups, so pressed keys cannot change the boot mode.
static const uint8_t ROW_PINS[MATRIX_ROWS] = {10, 20, 21};
static const uint8_t COL_PINS[MATRIX_COLS] = {2, 8, 9};

#define ENC_A_PIN  3
#define ENC_B_PIN  4
#define ENC_SW_PIN 5

#define OLED_SDA_PIN 6
#define OLED_SCL_PIN 7

// If turning right lowers the volume, set this instead of re-soldering.
#define ENC_REVERSE false

// Most EC11 encoders click once per full electrical cycle (20 detents and
// 20 pulses per turn). If yours needs two clicks per step, set this to true.
// If it jumps two steps per click, set it to false.
#define ENC_HALF_STEP false

// ============================================================================
// Display
// ============================================================================
#define OLED_ROTATE_180  false  // true if the text is upside down
#define OLED_CONTRAST    80     // 0-255; lower = dimmer and slower burn-in
#define OLED_SLEEP_MIN   10     // turn the screen off after this many minutes
                                // without use (0 = never); any key wakes it

// ============================================================================
// Timing
// ============================================================================
#define DEBOUNCE_MS        5    // ignore switch bounce shorter than this
#define LAYER_HOLD_MS      600  // hold the knob this long to change layer
#define TAP_MS             12   // how long a "tap" (encoder step) is held
#define TYPE_MS            20   // per key when typing text (RUN, SEARCH, TEXT)
#define RUN_DIALOG_MS      500  // wait for the Win+R box to open
#define SEARCH_OPEN_MS     700  // wait for the Start menu to open
#define SEARCH_RESULT_MS   900  // wait for Windows search to find the program
#define CLEAR_BONDS_HOLD   true // hold key 1 + knob while powering on to forget
                                // all paired computers

// ============================================================================
// Computer keyboard layout
// ============================================================================
// RUN, SEARCH and TEXT type characters, and which key gives ":" or "/"
// depends on the keyboard layout chosen in Windows. true = Swedish,
// false = US English.
#define KEYBOARD_LAYOUT_SE true

// ============================================================================
// Keymap
// ============================================================================
// Layout, seen from above with the display and USB cable at the back:
//
//        back (USB-C)
//   [ OLED ]    ( knob )
//   +----+----+----+
//   | 1  | 2  | 3  |
//   +----+----+----+
//   | 4  | 5  | 6  |
//   +----+----+----+
//   | 7  | 8  | 9  |
//   +----+----+----+
//        front
//
// Hold the knob for LAYER_HOLD_MS to step to the next layer. The display shows
// the layer name and the labels of all keys. The current layer is saved and
// restored after a power cycle.
//
// Actions (the first argument is the label on the display, max 7 characters;
// å, ä and ö work):
//   KEY("F13", KEY_F13)                   a single key
//   COMBO("Kopiera", MOD_CTRL, KEY_C)     key with modifiers (MOD_CTRL | MOD_SHIFT ...)
//   MEDIA("Play", MEDIA_PLAY_PAUSE)       media key
//   RUN("Gmail", "https://mail.google.com")
//                                         Windows: Win+R, types it, Enter. Opens
//                                         web addresses, programs and folders
//   SEARCH("Bambu", "bambu studio")       Windows: Start menu search, Enter.
//                                         Starts (or switches to) a program
//   TEXT("Hej", "hej\n")                  types text (no å, ä, ö)
//   NEXT_LAYER("Lager")                   switch layer
//   NONE                                  does nothing
//
// Keys send "key down" while held and "key up" on release, so push-to-talk
// style bindings work.

static const Layer LAYERS[] = {
  {
    // Layer 1: apps, copy/paste and Discord.
    //
    // Discord's own Ctrl+Shift+M / Ctrl+Shift+D only work while Discord has
    // focus, so keys 6 and 7 send F13 / F14, which no normal keyboard has.
    // Bind them once in Discord: User Settings -> Keybinds -> Add a Keybind ->
    // "Toggle Mute", click the shortcut field and press key 9; again with
    // "Toggle Deafen" and key 8. Discord keybinds work even when Discord is in
    // the background.
    "Apps",
    {
      SEARCH("Bambu",   "bambu studio"),             // 1: start Bambu Studio
      RUN("YouTube",    "https://www.youtube.com"),  // 2: YouTube in the browser
      RUN("Gmail",      "https://mail.google.com"),  // 3: Gmail in the browser
      COMBO("Kopiera",  MOD_CTRL, KEY_C),            // 4: copy
      COMBO("Klistra",  MOD_CTRL, KEY_V),            // 5: paste
      COMBO("Ångra",    MOD_CTRL, KEY_Z),            // 6: undo
      KEY("PrtSc",      KEY_PRINTSCREEN),            // 7: Print Screen
      KEY("Deafen",     KEY_F14),                    // 8: Discord Toggle Deafen (full mute)
      KEY("Mute",       KEY_F13),                    // 9: Discord Toggle Mute
    },
    MEDIA("Volym",   MEDIA_VOL_UP),    // turn right
    MEDIA("Volym",   MEDIA_VOL_DOWN),  // turn left
    MEDIA("Ljud av", MEDIA_MUTE),      // click
  },
  {
    // Layer 2: media and calls.
    "Media",
    {
      MEDIA("Förra",  MEDIA_PREV),
      MEDIA("Play",   MEDIA_PLAY_PAUSE),
      MEDIA("Nästa",  MEDIA_NEXT),
      COMBO("Mik",    MOD_CTRL | MOD_SHIFT, KEY_M),  // Teams: mute mic
      COMBO("Kamera", MOD_CTRL | MOD_SHIFT, KEY_O),  // Teams: camera on/off
      MEDIA("Stopp",  MEDIA_STOP),
      MEDIA("Kalk",   MEDIA_CALCULATOR),
      MEDIA("Webb",   MEDIA_WWW_HOME),
      MEDIA("Mail",   MEDIA_MAIL),
    },
    MEDIA("Volym", MEDIA_VOL_UP),
    MEDIA("Volym", MEDIA_VOL_DOWN),
    MEDIA("Play",  MEDIA_PLAY_PAUSE),
  },
  {
    // Layer 3: editing. The knob scrubs through undo/redo.
    "Redigera",
    {
      COMBO("Kopiera", MOD_CTRL, KEY_C),
      COMBO("Klistra", MOD_CTRL, KEY_V),
      COMBO("Klipp",   MOD_CTRL, KEY_X),
      COMBO("Spara",   MOD_CTRL, KEY_S),
      COMBO("Sök",     MOD_CTRL, KEY_F),
      COMBO("Allt",    MOD_CTRL, KEY_A),
      COMBO("Ny flik", MOD_CTRL, KEY_T),
      COMBO("Stäng",   MOD_CTRL, KEY_W),
      COMBO("Skrivb.", MOD_GUI,  KEY_D),  // show desktop
    },
    COMBO("Gör om", MOD_CTRL, KEY_Y),  // turn right: redo
    COMBO("Ångra",  MOD_CTRL, KEY_Z),  // turn left: undo
    KEY("Enter",    KEY_ENTER),
  },
};
