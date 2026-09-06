// desk-robot firmware — Milestone 5: an expressive face, a turning head, a
// speaker, a microphone, and a camera. Driven over USB serial (115200 baud,
// type `help`) and, when include/secrets.h exists, over WiFi by the brain.

#include <Arduino.h>
#include <U8g2lib.h>
#include <WiFi.h>
#include <Wire.h>

#include "camera.h"
#include "config.h"
#include "face.h"
#include "link.h"
#include "mic.h"
#include "servo_neck.h"
#include "speaker.h"

#if __has_include("secrets.h")
#include "secrets.h"
#define HAVE_BRAIN 1
#else
#define HAVE_BRAIN 0
#endif

// 1.3" SH1106 128x64 OLED over hardware I2C (SDA=D4/GPIO5, SCL=D5/GPIO6).
// R2 = rotated 180 degrees: the OLED is mounted upside down on the head.
U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R2, U8X8_PIN_NONE);

Face face(u8g2);
ServoNeck panNeck;
ServoNeck tiltNeck;
Link brainLink;
Speaker speaker;
Mic mic;
Camera camera;
uint32_t nextTempMs = 0;
volatile bool speakDonePending = false;  // set by the speaker task, sent from loop()

uint32_t lastFrameMs = 0;
uint32_t nextStateMs = 0;
bool demoMode = true;  // cycles emotions on its own; off while the brain is connected
uint32_t nextDemoEmotionMs = 0;
uint8_t demoEmotionIdx = 0;

void printHelp() {
  Serial.println(F("desk-robot commands:"));
  Serial.println(F("  emo <name>   neutral|happy|sad|angry|surprised|sleepy|thinking"));
  Serial.println(F("  pan <deg>    turn head, -60..60 (0 = center)"));
  Serial.println(F("  tilt <deg>   nod head, -30 (down)..40 (up), 0 = level"));
  Serial.println(F("  center       head to center on both axes"));
  Serial.println(F("  blink        blink now"));
  Serial.println(F("  sleep on|off eyes shut, breathing, Z's"));
  Serial.println(F("  demo on|off  idle life: auto blinks, glances, emotion changes"));
  Serial.println(F("  glance on|off  idle head glances only (off while tracking a face)"));
  Serial.println(F("  volume <0-1> speaker volume"));
  Serial.println(F("  beep         play a test tone through the speaker"));
  Serial.println(F("  mic on|off   stream the microphone to the brain"));
  Serial.println(F("  miclevel     print mic level for 3 s (talk to it)"));
  Serial.println(F("  stream on|off [fps]  stream camera JPEGs to the brain"));
  Serial.println(F("  snap         grab one frame and report its size"));
  Serial.println(F("  temp         chip temperature"));
  Serial.println(F("  help         this text"));
}

void handleCommand(String line) {
  line.trim();
  if (line.isEmpty()) return;

  int space = line.indexOf(' ');
  String cmd = (space < 0) ? line : line.substring(0, space);
  String arg = (space < 0) ? String() : line.substring(space + 1);
  cmd.toLowerCase();
  arg.trim();

  if (cmd == "help") {
    printHelp();
  } else if (cmd == "emo") {
    Emotion e;
    if (emotionFromName(arg.c_str(), e)) {
      face.setEmotion(e);
      Serial.printf("emotion: %s\n", emotionName(e));
    } else {
      Serial.println(F("unknown emotion — try: neutral happy sad angry surprised sleepy thinking"));
    }
  } else if (cmd == "pan") {
    panNeck.setTarget(arg.toFloat());
    Serial.printf("pan -> %.0f deg\n", panNeck.target());
  } else if (cmd == "tilt") {
    tiltNeck.setTarget(arg.toFloat());
    Serial.printf("tilt -> %.0f deg\n", tiltNeck.target());
  } else if (cmd == "center") {
    panNeck.setTarget(0);
    tiltNeck.setTarget(0);
    Serial.println(F("head -> center"));
  } else if (cmd == "blink") {
    face.blink();
  } else if (cmd == "sleep") {
    face.setAsleep(arg == "on");
    Serial.printf("sleep %s\n", face.asleep() ? "on" : "off");
  } else if (cmd == "speak_begin") {
    speaker.beginSpeech(static_cast<size_t>(arg.toInt()));
  } else if (cmd == "speak_end") {
    speaker.endSpeech();
  } else if (cmd == "volume") {
    speaker.setVolume(arg.toFloat());
    Serial.printf("volume -> %.2f\n", arg.toFloat());
  } else if (cmd == "beep") {
    // 0.4 s of 440 Hz so the amp can be checked without the brain.
    static int16_t tone[16000 * 4 / 10];
    for (size_t i = 0; i < sizeof(tone) / sizeof(tone[0]); ++i) {
      tone[i] = static_cast<int16_t>(8000 * sinf(2 * PI * 440 * i / 16000.0f));
    }
    speaker.beginSpeech();
    speaker.feed(reinterpret_cast<uint8_t*>(tone), sizeof(tone));
    speaker.endSpeech();
    Serial.println(F("beep"));
  } else if (cmd == "mic") {
    mic.setStreaming(arg == "on");
    Serial.printf("mic %s\n", mic.streaming() ? "on" : "off");
  } else if (cmd == "miclevel") {
    for (int i = 0; i < 12; ++i) {
      delay(250);
      int bars = static_cast<int>(mic.level() * 200);
      Serial.printf("  level %.3f %.*s\n", mic.level(), min(bars, 40), "########################################");
    }
  } else if (cmd == "stream") {
    int sp = arg.indexOf(' ');
    String onoff = sp < 0 ? arg : arg.substring(0, sp);
    float fps = sp < 0 ? 10.0f : arg.substring(sp + 1).toFloat();
    camera.setStreaming(onoff == "on", fps);
    Serial.printf("stream %s @ %.1f fps\n", camera.streaming() ? "on" : "off", fps);
  } else if (cmd == "snap") {
    if (!camera.ok()) {
      Serial.println(F("camera not available"));
    } else {
      bool was = camera.streaming();
      camera.setStreaming(true, 10);
      static uint8_t* jpg = static_cast<uint8_t*>(ps_malloc(64 * 1024));
      size_t n = 0;
      for (int i = 0; i < 40 && n == 0 && jpg; ++i) { delay(25); n = camera.takeFrame(jpg, 64 * 1024); }
      camera.setStreaming(was, 10);
      Serial.printf("snap: %u bytes (%s)\n", n, n ? "ok" : "no frame");
    }
  } else if (cmd == "temp") {
    Serial.printf("chip %.1f C\n", temperatureRead());
  } else if (cmd == "glance") {
    panNeck.setIdleGlances(arg == "on");
    tiltNeck.setIdleGlances(arg == "on");
    Serial.printf("glance %s\n", arg == "on" ? "on" : "off");
  } else if (cmd == "demo") {
    demoMode = (arg == "on");
    face.setIdle(demoMode);
    panNeck.setIdleGlances(demoMode);
    tiltNeck.setIdleGlances(demoMode);
    Serial.printf("demo %s\n", demoMode ? "on" : "off");
  } else {
    Serial.println(F("unknown command — type `help`"));
  }
}

void setup() {
  Serial.begin(115200);
  randomSeed(esp_random());

  // ESP32Servo wants its LEDC timers claimed up front.
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);

  face.begin();
  panNeck.begin(PIN_SERVO_PAN, PAN_MIN_DEG, PAN_MAX_DEG, PAN_MAX_SPEED,
                SERVO_RELAX_MS, PAN_TRIM_DEG, /*glanceRange=*/25.0f);
  tiltNeck.begin(PIN_SERVO_TILT, TILT_MIN_DEG, TILT_MAX_DEG, TILT_MAX_SPEED,
                 SERVO_RELAX_MS, TILT_TRIM_DEG, /*glanceRange=*/10.0f,
                 TILT_INVERT);

  speaker.begin(PIN_I2S_BCLK, PIN_I2S_LRC, PIN_I2S_DIN, SPEAKER_VOLUME,
                []() { speakDonePending = true; });
  mic.begin(PIN_PDM_CLK, PIN_PDM_DATA, MIC_GAIN);
  if (camera.begin()) Serial.println(F("camera: ready"));

  demoMode = true;
  face.setIdle(true);
  panNeck.setIdleGlances(true);
  tiltNeck.setIdleGlances(true);
  nextDemoEmotionMs = millis() + 8000;

  Serial.println(F("\ndesk-robot v0.3.0 — hello!"));
  printHelp();

#if HAVE_BRAIN
  brainLink.onAudio([](const uint8_t* pcm, size_t len) { speaker.feed(pcm, len); });
#ifndef ROBOT_TOKEN
#define ROBOT_TOKEN ""
#endif
  brainLink.begin(WIFI_SSID, WIFI_PASS, BRAIN_HOST, BRAIN_PORT, ROBOT_TOKEN,
             [](const String& cmd) { handleCommand(cmd); },
             [](bool connected) {
               // The brain picks emotions while it's connected; the demo
               // cycle takes over again if it goes away. Blinks and idle
               // glances stay on either way.
               demoMode = !connected;
               if (connected) {
                 face.setEmotion(Emotion::Happy);
               }
             });
#else
  Serial.println(F("no include/secrets.h — USB-only mode (see secrets.h.example)"));
#endif
}

void loop() {
  // Serial console.
  static String lineBuf;
  while (Serial.available()) {
    char c = static_cast<char>(Serial.read());
    if (c == '\n' || c == '\r') {
      if (!lineBuf.isEmpty()) handleCommand(lineBuf);
      lineBuf = "";
    } else if (lineBuf.length() < 80) {
      lineBuf += c;
    }
  }

  uint32_t now = millis();

#if HAVE_BRAIN
  brainLink.update(now);
  if (speakDonePending) {
    speakDonePending = false;
    brainLink.sendJson("{\"type\":\"speak_done\"}");
    Serial.printf("speech: %u underruns, prebuffered %u bytes in %u ms, wifi %d dBm\n",
                  speaker.lastUnderruns(), speaker.lastPrebuffered(),
                  speaker.lastPrebufferMs(), WiFi.RSSI());
  }
  {
    static uint8_t frame[Mic::FRAME_BYTES];
    while (brainLink.connected() && mic.nextFrame(frame)) {
      brainLink.sendBinary(0x01, frame, sizeof(frame));
    }
  }
  if (brainLink.connected() && camera.streaming()) {
    static uint8_t* jpg = static_cast<uint8_t*>(ps_malloc(64 * 1024));
    size_t n = jpg ? camera.takeFrame(jpg, 64 * 1024) : 0;
    if (n > 0) brainLink.sendBinary(0x02, jpg, n);
  }
  if (brainLink.connected() && now >= nextTempMs) {
    nextTempMs = now + 10000;
    brainLink.sendJson(String("{\"type\":\"temp\",\"c\":") + String(temperatureRead(), 1) + "}");
  }
  if (brainLink.connected() && now >= nextStateMs) {
    nextStateMs = now + 5000;
    brainLink.sendState(panNeck.current(), emotionName(face.emotion()));
  }
#endif

  // Demo mode: wander through emotions so a fresh flash shows everything.
  if (demoMode && now >= nextDemoEmotionMs) {
    static const Emotion cycle[] = {
        Emotion::Neutral, Emotion::Happy,     Emotion::Thinking,
        Emotion::Neutral, Emotion::Surprised, Emotion::Sleepy,
    };
    demoEmotionIdx = (demoEmotionIdx + 1) % (sizeof(cycle) / sizeof(cycle[0]));
    face.setEmotion(cycle[demoEmotionIdx]);
    nextDemoEmotionMs = now + random(6000, 12000);
  }

  if (now - lastFrameMs >= FRAME_INTERVAL_MS) {
    lastFrameMs = now;
    face.setTalking(speaker.speaking(), speaker.level());
    face.update(now);
    panNeck.update(now);
    tiltNeck.update(now);
  }
}
