# desk-robot

A small expressive desk robot: an OLED face on a pan-tilt neck, with a camera,
microphone, speaker, and a cloud AI brain.

## Architecture

```
┌──────────────── the robot (XIAO ESP32S3 Sense) ───────────────┐
│  OLED face · pan servo · camera · PDM mic · I2S amp + speaker │
└───────────────────────────┬───────────────────────────────────┘
                            │ WiFi (WebSocket)
┌───────────────────────────┴───────────────────────────────────┐
│  brain server (Python, runs on the Mac)                       │
│  wake word → speech-to-text → LLM (OpenRouter) → text-to-speech│
│  also decides emotions + head movements                       │
└───────────────────────────────────────────────────────────────┘
```

The ESP32 is the body; the intelligence lives in `server/` and calls a
language model through OpenRouter. Nothing is billed while the robot is idle.

## Repo layout

- `firmware/` — PlatformIO project for the XIAO ESP32S3 Sense
- `server/` — Python brain server for the Mac
- `docs/wiring.md` — how to hook everything up (read before powering on!)
- `docs/protocol.md` — the WebSocket protocol between robot and brain

## Milestones

- [x] **M1 — Alive**: OLED face animation + pan & tilt servos with easing
      (no WiFi needed; drive it over the USB serial monitor)
- [x] **M2 — Connected**: firmware joins WiFi, server pushes emotions/pan/tilt
- [x] **M4 (Mac prototype) — Wake word**: "hey Rocky" → question → spoken
      reply, all on the Mac's mic + speaker (`server/brain/ears.py`, `mouth.py`)
- [x] **M3 — Voice on the robot**: robot mic audio streams to the server and
      Rocky's voice plays through the robot's speaker (same pipeline, new
      audio in/out)
- [ ] **M5 — Vision**: live camera stream to the Mac (small frames, ~10 fps),
      a live-view page in the browser, and face tracking so the head
      follows you; Claude sees the latest frame when you talk to it
- [ ] **M6 — Shell**: a 3D-printed head/body so the robot has a look, not
      just guts

The firmware in this repo implements **M1 + M2**: flash it with no
`secrets.h` and the robot blinks at you over USB; add `secrets.h` and it
joins WiFi and takes orders from Rocky's brain on the Mac.

## Firmware quickstart

1. Install PlatformIO — easiest is the **PlatformIO IDE** extension in
   VS Code, or on the command line:

   ```bash
   brew install platformio
   ```

2. Wire up the OLED and servo per `docs/wiring.md`.

3. Plug the XIAO in over USB-C, then:

   ```bash
   cd firmware
   pio run -t upload      # build + flash
   pio device monitor     # open the serial console @115200
   ```

   To connect it to the brain, copy `firmware/include/secrets.h.example` to
   `secrets.h`, fill in your 2.4 GHz WiFi name/password and the Mac's IP
   (`ipconfig getifaddr en0`), and flash again. The serial monitor shows
   `wifi: connected` and then `brain: connected` once the server is running.
   Without `secrets.h` the firmware stays in USB-only mode.

4. In the serial monitor, try:

   ```
   help                 list commands
   emo happy            change the face (neutral/happy/sad/angry/surprised/sleepy/thinking)
   pan -30              turn the head (degrees, -60..60, 0 = center)
   tilt 20              nod the head (degrees, -30 down..40 up, 0 = level)
   blink                manual blink
   demo off             stop the idle demo behavior
   raw tilt 20          calibration move that ignores the limits (watch it!)
   ```

On boot the robot runs an idle "alive" behavior: blinking and occasionally
changing expression, so you can see everything working without typing
anything. The head only moves when told to (by you, the brain, or face
tracking); the brain switches the firmware's idle glances off on connect
because they fought deliberate looks.

## Brain server quickstart

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                  # then put your OpenRouter key in .env
python -m brain.main
```

The server listens through the robot's microphone when the robot is
connected, and the Mac's microphone otherwise. Rocky's replies play through
the robot's speaker when it's connected, else the Mac's. Say
**"hey Rocky"** and then your question; Rocky answers out loud. Once awake
he keeps listening without his name; after a minute with nothing from you
he dozes off (sleepy face). Say **"Rocky, sleep"** (or "goodnight") to put
him down right away. (macOS will ask once to let your terminal use the
microphone.)

Conversation is meant to feel natural rather than push-to-talk:

- He decides you're done the way a person does. A small model
  (Smart Turn, in `server/brain/turn.py`) listens to how your sentence
  ends; if you sound finished he answers about a third of a second later,
  and if you trail off mid-thought he waits (up to `TURN_MAX_SILENCE`).
- His reply streams: the first sentence is spoken while the rest is still
  being written, so the first word arrives a couple of seconds after yours.
- If you start talking again before he speaks, he drops the reply, hears
  the rest, and answers the whole thing once. Once he *is* speaking he
  finishes the line — his mic is muted while his own voice plays (no echo
  cancellation yet).

Every reply prints a `timing` line so you can see where the time goes.

The live view at http://localhost:8766/ is Rocky's console: what he sees
(with a reticle showing where his head points), what he hears (a rolling
sound strip, gold for speech, red while he talks), the last exchange, and
controls for his head, face, voice, sleep, and the listening knobs above.
Slider changes apply immediately and last until the server restarts; put
the value in `server/brain/config.py` to keep it. The page only answers
requests from this Mac, and its controls require a header a foreign web
page cannot send.

You can also type in the server console:

```
ask what is a weekend?         talk to Rocky from your keyboard
listen                         toggle microphone listening on/off
mic                            3-second level meter to check the microphone
emo surprised                  push a face to the robot (once M2 lands)
pan 20                         push a head turn (once M2 lands)
```

None of this needs the robot hardware, so you can tune the personality in
`server/brain/personality.py` right now. Listening knobs (which mic, how
eagerly he decides you're finished, the speech model) are in
`server/brain/config.py`. Speech-to-text and turn detection run locally on
the Mac (faster-whisper, Silero VAD, Smart Turn); the first run downloads
~160 MB of models.

The model is an OpenRouter model id in `server/brain/config.py`
(`anthropic/claude-haiku-4.5` by default, a few dollars a month of chatting).
One OpenRouter key works for every model, so swapping is a one-line change.

## The robot is Rocky

The personality in `server/brain/personality.py` is Rocky, the Eridian
engineer from *Project Hail Mary*: short sentences, "question"/"answer",
"amaze", and constant worry about whether his human has slept. Tune him by
chatting with `ask` in the server console and adding good exchanges to the
example replies. The wake word (M4) will be "hey Rocky".

The voice (M3) comes from Fish Audio's community Rocky voice — set
`TTS_VOICE_ID` in `server/brain/config.py` and export `FISH_AUDIO_API_KEY`.

## Security notes

- **Secrets live in two git-ignored files**: `server/.env` (API keys,
  `ROBOT_TOKEN`) and `firmware/include/secrets.h` (WiFi, brain address,
  `ROBOT_TOKEN`). Never commit them, and don't share `firmware/.pio/`
  build output either: the compiled binary contains the WiFi password.
- **Only your robot can talk to the brain.** The WebSocket port is open to
  the LAN (the robot needs it), but the first message must carry
  `ROBOT_TOKEN`; anything else is dropped. One robot at a time.
- **The camera live view is this Mac only** (`LIVE_VIEW_BIND` in
  `config.py`). Opening it to the LAN would let anyone on the WiFi watch
  the camera and read transcripts.
- **Voice is unauthenticated by design**: anyone in earshot can say "hey
  Rocky". His abilities are limited to moving his head; each reply costs a
  fraction of a cent. "Rocky, sleep" or a quiet minute puts him down.
- **What leaves the Mac:** each question sends the transcript, the recent
  conversation, and the newest camera frame to OpenRouter (and on to the
  model provider); each reply's text goes to Fish Audio. Speech-to-text and
  face tracking run locally. Nothing is stored by the server except
  in-memory history (`MAX_HISTORY_TURNS`).
- Traffic to OpenRouter and Fish Audio is HTTPS. Robot ↔ Mac traffic is
  plain WebSocket on your home network (no TLS in v1). Known limitation:
  the robot trusts whatever answers at `BRAIN_HOST`, so someone already on
  your WiFi who spoofs the Mac's address could command the robot and
  receive its mic/camera streams. Mutual authentication or WSS is the v2 fix.
- The macOS `say` fallback voice receives text on stdin, never as an
  argument, so a reply beginning with "-" can't turn into options.
- The live view rejects requests whose `Host` header isn't a local name
  (DNS-rebinding guard).
