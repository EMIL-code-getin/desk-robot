// Bluetooth LE HID: makes the ESP32-C6 look like a keyboard with media keys.
//
// The ESP32-C6 has no USB device peripheral (only USB serial/JTAG), so it
// cannot be a USB keyboard. Bluetooth works with Windows, macOS, Linux,
// Android and iOS without any driver or companion app.
#pragma once
#include <stdint.h>

namespace BleHid {

void begin(const char* deviceName, const char* manufacturer);
bool connected();

// Keyboard report: modifier mask plus up to 6 pressed keys (0 = empty slot).
void sendKeys(uint8_t mods, const uint8_t keys[6]);

// Consumer report: one media usage, 0 = released.
void sendMedia(uint16_t usage);

// Forget every paired computer (they must pair again).
void clearBonds();

}  // namespace BleHid
