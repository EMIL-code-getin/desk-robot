// What a key or encoder movement does. Build actions with the macros below;
// config.h uses them to describe the keymap. The first argument of every
// macro is the label shown on the OLED (keep it to 7 characters).
#pragma once
#include <stdint.h>
#include "keycodes.h"

enum ActionType : uint8_t {
  ACT_NONE,
  ACT_KEY,    // keyboard key, optionally with modifiers; held while pressed
  ACT_MEDIA,  // consumer/media key (volume, play/pause...); held while pressed
  ACT_TEXT,   // types a short string (ASCII letters, digits, space, Enter)
  ACT_LAYER,  // jump to the next layer
};

struct Action {
  ActionType type;
  uint8_t mods;       // MOD_* bit mask for ACT_KEY
  uint16_t code;      // KEY_* for ACT_KEY, MEDIA_* for ACT_MEDIA
  const char* text;   // for ACT_TEXT
  const char* label;  // shown on the display
};

#define NONE                {ACT_NONE, 0, 0, nullptr, ""}
#define KEY(lbl, k)         {ACT_KEY, 0, (k), nullptr, (lbl)}
#define COMBO(lbl, m, k)    {ACT_KEY, (m), (k), nullptr, (lbl)}
#define MEDIA(lbl, u)       {ACT_MEDIA, 0, (u), nullptr, (lbl)}
#define TEXT(lbl, s)        {ACT_TEXT, 0, 0, (s), (lbl)}
#define NEXT_LAYER(lbl)     {ACT_LAYER, 0, 0, nullptr, (lbl)}

#define MATRIX_ROWS 3
#define MATRIX_COLS 3
#define NUM_KEYS (MATRIX_ROWS * MATRIX_COLS)

struct Layer {
  const char* name;       // shown in the display header
  Action keys[NUM_KEYS];  // key 1..9, row by row from the display side
  Action turnRight;       // one detent clockwise (its label is shown as "Vrid")
  Action turnLeft;        // one detent counter-clockwise
  Action encoderClick;    // short press on the knob
};
