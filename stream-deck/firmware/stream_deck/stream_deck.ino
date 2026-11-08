// Stream deck: 9 keys + rotary encoder + 0.96" OLED, Seeed XIAO ESP32C3,
// Bluetooth keyboard with media keys.
//
// Arduino IDE settings (Tools menu):
//   Board:            XIAO_ESP32C3   (package "esp32" by Espressif, 3.x)
//   USB CDC On Boot:  Enabled
// Libraries (Library Manager):
//   NimBLE-Arduino by h2zero, version 2.x
//   U8g2 by oliver
//
// What every key does, the Bluetooth name and the pins are in the config.h tab.
// The rest of the program is in deck.cpp, ble_hid.cpp and display.cpp.

#include "deck.h"

void setup() {
  deck::setup();
}

void loop() {
  deck::loop();
}
