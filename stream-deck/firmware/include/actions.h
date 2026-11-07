// What a key or encoder movement does. Build actions with the macros below;
// config.h uses them to describe the keymap.
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
  uint8_t mods;      // MOD_* bit mask for ACT_KEY
  uint16_t code;     // KEY_* for ACT_KEY, MEDIA_* for ACT_MEDIA
  const char* text;  // for ACT_TEXT
};

#define NONE          {ACT_NONE, 0, 0, nullptr}
#define KEY(k)        {ACT_KEY, 0, (k), nullptr}
#define COMBO(m, k)   {ACT_KEY, (m), (k), nullptr}
#define MEDIA(u)      {ACT_MEDIA, 0, (u), nullptr}
#define TEXT(s)       {ACT_TEXT, 0, 0, (s)}
#define NEXT_LAYER    {ACT_LAYER, 0, 0, nullptr}

#define NUM_KEYS 6

struct Layer {
  const char* name;
  Action keys[NUM_KEYS];  // key 1..6, see the layout drawing in config.h
  Action turnRight;       // one detent clockwise
  Action turnLeft;        // one detent counter-clockwise
  Action encoderClick;    // short press on the knob
};
