#include "display.h"

#include <Arduino.h>
#include <U8g2lib.h>
#include <Wire.h>

#include "config.h"

namespace {

// Full-buffer mode: 1 KB of RAM, one I2C transfer (~25 ms) per redraw.
U8G2_SSD1306_128X64_NONAME_F_HW_I2C oled(OLED_ROTATE_180 ? U8G2_R2 : U8G2_R0,
                                         U8X8_PIN_NONE);

bool present = false;     // false if the display did not answer on I2C
bool sleeping = false;
bool dirty = true;
uint32_t lastActivity = 0;
uint32_t lastDraw = 0;

// Temporary overlays (message or layer banner) until this time.
enum class Overlay : uint8_t { None, Message, Banner };
Overlay overlay = Overlay::None;
uint32_t overlayUntil = 0;
char overlayLine1[24];
char overlayLine2[24];

Display::State lastState{};
bool lastBlink = false;

constexpr int CELL_W = 42;   // 3 columns x 42 px + 2 px gaps = 128
constexpr int CELL_H = 13;
constexpr int GRID_TOP = 12;

// Draw `text` centred in [x, x+w), shrinking the font if it is too wide.
void drawCentered(const char* text, int x, int w, int baseline) {
  oled.setFont(u8g2_font_6x10_tf);
  int tw = oled.getUTF8Width(text);
  if (tw > w) {
    oled.setFont(u8g2_font_5x8_tf);
    tw = oled.getUTF8Width(text);
  }
  oled.drawUTF8(x + (w - tw) / 2, baseline, text);
}

void drawMain(const Layer& layer, const Display::State& s, bool blink) {
  oled.clearBuffer();

  // Header: layer name, layer number and Bluetooth status.
  oled.setFont(u8g2_font_6x10_tf);
  oled.drawUTF8(0, 8, layer.name);
  char status[16];
  if (s.connected) {
    snprintf(status, sizeof(status), "%u/%u BT", s.layer + 1, s.numLayers);
  } else {
    snprintf(status, sizeof(status), "%s", blink ? "Söker BT" : "");
  }
  oled.drawUTF8(128 - oled.getUTF8Width(status), 8, status);
  oled.drawHLine(0, 10, 128);

  // 3x3 key grid. Held keys are drawn inverted.
  for (uint8_t i = 0; i < NUM_KEYS; i++) {
    int col = i % MATRIX_COLS;
    int row = i / MATRIX_COLS;
    int x = col * (CELL_W + 1);
    int y = GRID_TOP + row * CELL_H;
    bool held = s.pressedKeys & (1u << i);
    if (held) {
      oled.drawRBox(x, y, CELL_W, CELL_H - 1, 2);
      oled.setDrawColor(0);
    }
    drawCentered(layer.keys[i].label, x, CELL_W, y + 10);
    oled.setDrawColor(1);
  }

  // Footer: what turning and clicking the knob does.
  oled.drawHLine(0, 52, 128);
  oled.setFont(u8g2_font_5x8_tf);
  char turn[24];
  char click[24];
  snprintf(turn, sizeof(turn), "Vrid: %s", layer.turnRight.label);
  snprintf(click, sizeof(click), "Klick: %s", layer.encoderClick.label);
  if (oled.getUTF8Width(turn) + oled.getUTF8Width(click) + 4 > 128) {
    snprintf(turn, sizeof(turn), "<> %s", layer.turnRight.label);
    snprintf(click, sizeof(click), "* %s", layer.encoderClick.label);
  }
  oled.drawUTF8(0, 62, turn);
  int cw = oled.getUTF8Width(click);
  if (s.knobPressed) {
    oled.drawBox(128 - cw - 2, 54, cw + 2, 10);
    oled.setDrawColor(0);
  }
  oled.drawUTF8(128 - cw - 1, 62, click);
  oled.setDrawColor(1);

  oled.sendBuffer();
}

void drawOverlay(bool banner) {
  oled.clearBuffer();
  oled.drawRFrame(0, 0, 128, 64, 4);
  oled.setFont(banner ? u8g2_font_helvB14_tf : u8g2_font_7x13B_tf);
  int w = oled.getUTF8Width(overlayLine1);
  oled.drawUTF8((128 - w) / 2, 30, overlayLine1);
  oled.setFont(u8g2_font_6x10_tf);
  w = oled.getUTF8Width(overlayLine2);
  oled.drawUTF8((128 - w) / 2, 50, overlayLine2);
  oled.sendBuffer();
}

void setOverlay(Overlay kind, const char* l1, const char* l2, uint32_t ms) {
  snprintf(overlayLine1, sizeof(overlayLine1), "%s", l1);
  snprintf(overlayLine2, sizeof(overlayLine2), "%s", l2);
  overlay = kind;
  overlayUntil = millis() + ms;
  dirty = true;
  Display::activity();
}

}  // namespace

namespace Display {

void begin() {
  Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN);
  // Probe the usual SSD1306 address before handing the bus to U8g2, so a
  // missing or miswired display does not stall the keys.
  Wire.beginTransmission(0x3C);
  present = Wire.endTransmission() == 0;
  if (!present) {
    Serial.println("[oled] no display at 0x3C, running without it");
    return;
  }
  oled.setBusClock(400000);
  oled.begin();
  oled.setContrast(OLED_CONTRAST);
  lastActivity = millis();
  Serial.println("[oled] ok");
}

void message(const char* line1, const char* line2, uint32_t ms) {
  setOverlay(Overlay::Message, line1, line2, ms);
  if (present) drawOverlay(false);  // show it right away (used during boot)
}

void layerBanner(const Layer& layer, uint8_t index, uint8_t count) {
  char sub[24];
  snprintf(sub, sizeof(sub), "Lager %u av %u", index + 1, count);
  setOverlay(Overlay::Banner, layer.name, sub, 900);
}

void activity() {
  lastActivity = millis();
  if (sleeping && present) {
    oled.setPowerSave(0);
    sleeping = false;
    dirty = true;
  }
}

void update(const Layer& layer, const State& s) {
  if (!present) return;
  uint32_t now = millis();

  if (OLED_SLEEP_MIN > 0 && !sleeping &&
      now - lastActivity > uint32_t(OLED_SLEEP_MIN) * 60000UL) {
    oled.setPowerSave(1);
    sleeping = true;
  }
  if (sleeping) return;

  if (overlay != Overlay::None) {
    if (int32_t(now - overlayUntil) >= 0) {
      overlay = Overlay::None;
      dirty = true;
    } else {
      if (dirty) {
        drawOverlay(overlay == Overlay::Banner);
        dirty = false;
        lastDraw = now;
      }
      return;
    }
  }

  bool blink = (now / 600) % 2 == 0;
  if (s.layer != lastState.layer || s.connected != lastState.connected ||
      s.pressedKeys != lastState.pressedKeys ||
      s.knobPressed != lastState.knobPressed ||
      (!s.connected && blink != lastBlink)) {
    dirty = true;
  }
  // Limit redraws so a burst of key presses does not hog the loop.
  if (!dirty || now - lastDraw < 30) return;

  drawMain(layer, s, blink);
  lastState = s;
  lastBlink = blink;
  dirty = false;
  lastDraw = now;
}

}  // namespace Display
