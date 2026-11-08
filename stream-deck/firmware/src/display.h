// 0.96" 128x64 SSD1306 OLED: shows the layer, Bluetooth status and what every
// key and the knob do.
#pragma once
#include <stdint.h>

#include "actions.h"

namespace Display {

struct State {
  uint8_t layer;          // index into LAYERS
  uint8_t numLayers;
  bool connected;         // Bluetooth link to a computer
  uint16_t pressedKeys;   // bit i = key i+1 held
  bool knobPressed;
};

void begin();

// Show a message for `ms` milliseconds (two short lines, second may be "").
void message(const char* line1, const char* line2, uint32_t ms);

// Show the layer name large for a moment after switching layers.
void layerBanner(const Layer& layer, uint8_t index, uint8_t count);

// Call on every key press or knob movement: wakes the screen and resets the
// sleep timer.
void activity();

// Redraws when something changed. Call from loop().
void update(const Layer& layer, const State& state);

}  // namespace Display
