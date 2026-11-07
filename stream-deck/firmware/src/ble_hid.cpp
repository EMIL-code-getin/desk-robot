#include "ble_hid.h"

#include <Arduino.h>
#include <NimBLEDevice.h>
#include <NimBLEHIDDevice.h>

namespace {

constexpr uint8_t REPORT_ID_KEYBOARD = 1;
constexpr uint8_t REPORT_ID_MEDIA = 2;

// HID report descriptor: a keyboard (report 1) and a consumer-control device
// for media keys (report 2).
uint8_t kReportMap[] = {
  // ---- Keyboard ----
  0x05, 0x01,        // Usage Page (Generic Desktop)
  0x09, 0x06,        // Usage (Keyboard)
  0xA1, 0x01,        // Collection (Application)
  0x85, REPORT_ID_KEYBOARD,
  0x05, 0x07,        //   Usage Page (Key Codes)
  0x19, 0xE0,        //   Usage Minimum (Left Control)
  0x29, 0xE7,        //   Usage Maximum (Right GUI)
  0x15, 0x00,        //   Logical Minimum (0)
  0x25, 0x01,        //   Logical Maximum (1)
  0x75, 0x01,        //   Report Size (1)
  0x95, 0x08,        //   Report Count (8)
  0x81, 0x02,        //   Input (Data, Var, Abs)      modifier bits
  0x95, 0x01,        //   Report Count (1)
  0x75, 0x08,        //   Report Size (8)
  0x81, 0x01,        //   Input (Const)               reserved byte
  0x95, 0x05,        //   Report Count (5)
  0x75, 0x01,        //   Report Size (1)
  0x05, 0x08,        //   Usage Page (LEDs)
  0x19, 0x01,        //   Usage Minimum (Num Lock)
  0x29, 0x05,        //   Usage Maximum (Kana)
  0x91, 0x02,        //   Output (Data, Var, Abs)     LED report
  0x95, 0x01,        //   Report Count (1)
  0x75, 0x03,        //   Report Size (3)
  0x91, 0x01,        //   Output (Const)              padding
  0x95, 0x06,        //   Report Count (6)
  0x75, 0x08,        //   Report Size (8)
  0x15, 0x00,        //   Logical Minimum (0)
  0x25, 0x73,        //   Logical Maximum (0x73 = F24)
  0x05, 0x07,        //   Usage Page (Key Codes)
  0x19, 0x00,        //   Usage Minimum (0)
  0x29, 0x73,        //   Usage Maximum (0x73)
  0x81, 0x00,        //   Input (Data, Array)         6 key slots
  0xC0,              // End Collection

  // ---- Media keys ----
  0x05, 0x0C,        // Usage Page (Consumer)
  0x09, 0x01,        // Usage (Consumer Control)
  0xA1, 0x01,        // Collection (Application)
  0x85, REPORT_ID_MEDIA,
  0x15, 0x00,        //   Logical Minimum (0)
  0x26, 0xFF, 0x03,  //   Logical Maximum (0x3FF)
  0x19, 0x00,        //   Usage Minimum (0)
  0x2A, 0xFF, 0x03,  //   Usage Maximum (0x3FF)
  0x75, 0x10,        //   Report Size (16)
  0x95, 0x01,        //   Report Count (1)
  0x81, 0x00,        //   Input (Data, Array)
  0xC0,              // End Collection
};

NimBLEServer* gServer = nullptr;
NimBLEHIDDevice* gHid = nullptr;
NimBLECharacteristic* gKeyboardInput = nullptr;
NimBLECharacteristic* gMediaInput = nullptr;
volatile bool gConnected = false;

class ServerCallbacks : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer* server, NimBLEConnInfo& info) override {
    Serial.printf("[ble] connected: %s\n", info.getAddress().toString().c_str());
    gConnected = true;
  }

  void onDisconnect(NimBLEServer* server, NimBLEConnInfo& info, int reason) override {
    // advertiseOnDisconnect(true) restarts advertising for us.
    Serial.printf("[ble] disconnected (reason %d), advertising again\n", reason);
    gConnected = server->getConnectedCount() > 0;
  }

  void onAuthenticationComplete(NimBLEConnInfo& info) override {
    Serial.printf("[ble] pairing %s, bonded=%d\n",
                  info.isEncrypted() ? "ok" : "FAILED", info.isBonded());
  }
};

ServerCallbacks gCallbacks;

void notify(NimBLECharacteristic* chr, const uint8_t* data, size_t len) {
  if (!gConnected || chr == nullptr) return;
  chr->setValue(data, len);
  chr->notify();
}

}  // namespace

namespace BleHid {

void begin(const char* deviceName, const char* manufacturer) {
  NimBLEDevice::init(deviceName);
  NimBLEDevice::setPower(9);  // dBm; a desk is not a large room

  // "Just works" pairing with bonding: no PIN prompt, and the computer
  // reconnects on its own after the deck is powered off and on.
  NimBLEDevice::setSecurityAuth(/*bonding*/ true, /*mitm*/ false, /*sc*/ true);
  NimBLEDevice::setSecurityIOCap(BLE_HS_IO_NO_INPUT_OUTPUT);

  gServer = NimBLEDevice::createServer();
  gServer->setCallbacks(&gCallbacks, false);
  gServer->advertiseOnDisconnect(true);

  gHid = new NimBLEHIDDevice(gServer);
  gHid->setManufacturer(manufacturer);
  // USB-IF "test" vendor/product id; the computer only uses it for display.
  gHid->setPnp(0x02, 0xE502, 0xA111, 0x0210);
  gHid->setHidInfo(0x00, 0x01);  // no country code; remote wake
  gHid->setReportMap(kReportMap, sizeof(kReportMap));

  gKeyboardInput = gHid->getInputReport(REPORT_ID_KEYBOARD);
  gHid->getOutputReport(REPORT_ID_KEYBOARD);  // Caps/Num lock LEDs (ignored)
  gMediaInput = gHid->getInputReport(REPORT_ID_MEDIA);

  gHid->setBatteryLevel(100);
  gHid->startServices();

  NimBLEAdvertising* adv = NimBLEDevice::getAdvertising();
  adv->setAppearance(0x03C1);  // HID keyboard
  adv->addServiceUUID(gHid->getHidService()->getUUID());
  adv->setName(deviceName);
  adv->start();

  Serial.printf("[ble] advertising as \"%s\"\n", deviceName);
}

bool connected() { return gConnected; }

void sendKeys(uint8_t mods, const uint8_t keys[6]) {
  uint8_t report[8] = {mods, 0, keys[0], keys[1], keys[2], keys[3], keys[4], keys[5]};
  notify(gKeyboardInput, report, sizeof(report));
}

void sendMedia(uint16_t usage) {
  uint8_t report[2] = {uint8_t(usage & 0xFF), uint8_t(usage >> 8)};
  notify(gMediaInput, report, sizeof(report));
}

void clearBonds() {
  NimBLEDevice::deleteAllBonds();
}

}  // namespace BleHid
