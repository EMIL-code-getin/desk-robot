# Robot ↔ brain WebSocket protocol (v0)

The robot connects to `ws://<mac-ip>:8765`. The first message must be a
`hello` carrying the shared `ROBOT_TOKEN` (server/.env, firmware secrets.h);
the server drops anything else without replying, and allows one robot at a
time. Plain `ws://` on the home LAN — no TLS in v1. Text frames are JSON. Binary
frames start with one type byte: `0x01` = mic audio, `0x02` = camera JPEG
(M5). The rest of the frame is the payload.

## Robot → server

```json
{"type": "hello", "who": "desk-robot", "fw": "0.3.0", "token": "..."}  // must be the first message; token = ROBOT_TOKEN
{"type": "state", "pan": 12.5, "emotion": "neutral"}
{"type": "wake"}                  // wake word heard (M4, if detected on-device)
{"type": "temp", "c": 52.0}       // chip temperature, sent every ~10 s (M5)
{"type": "speak_done"}            // finished playing the last reply (M3)
```

Binary `0x01` frames (M3+): microphone audio, 16 kHz mono signed 16-bit PCM,
little-endian, ~20–60ms per frame.

Binary `0x02` frames (M5): one camera JPEG per frame, QVGA (320×240) by
default, sent continuously at `fps` while streaming is on. The server keeps
the latest frame for the live-view page, the face tracker, and Claude.

## Server → robot

```json
{"type": "emotion", "name": "happy"}
{"type": "pan", "deg": -20}
{"type": "tilt", "deg": 15}
{"type": "speak_begin", "bytes": 96000}  // binary TTS audio frames follow (M3); bytes = total, so the robot can pre-buffer
{"type": "speak_end"}             // no more audio; robot replies speak_done when played out
{"type": "volume", "level": 0.4}  // speaker volume 0.0-1.0 (M3)
{"type": "asleep", "on": true}    // eyes shut + Z's; false = wake up
{"type": "stream", "on": true, "fps": 10}   // start/stop the camera stream, set rate (M5)
```

The server sends `stream on` at `CAMERA_FPS` when the robot connects. The
live view is served by `server/brain/eyes.py` at http://localhost:8766/.

Binary frames (M3+): type byte `0x01` then TTS audio for the speaker, same
PCM format as above, ~100 ms per frame. The robot buffers the whole reply
(PSRAM) and plays it out; the server waits for `speak_done` before it
un-mutes the microphone.

Firmware side: `firmware/src/link.cpp` maps each server message onto the
same text commands the USB console uses (`emo`, `pan`, `tilt`), so both
paths behave identically. The robot sends `state` every 5 s.

Keep this file in sync with `firmware/src/link.cpp` and `server/brain/main.py`
whenever a message type is added.
