"""desk-robot brain server.

Run with:  python -m brain.main   (from the server/ directory, venv active)

Three jobs:
  1. WebSocket server the robot connects to over WiFi (Milestone 2+).
  2. An interactive console so you can talk to the brain and puppet the
     robot from your keyboard right now.
  3. Listening: hears "hey Rocky" on the Mac's mic, sends what you say to
     Claude, and speaks the reply (Mac speaker now, robot speaker in M3).

Console commands:
  ask <question>   send a question to the brain, print and speak the reply
  say <text>       speak text (robot speaker if connected, else the Mac)
  volume <0-1>     set the robot's speaker volume
  track on|off     face tracking (head follows you)
  listen           toggle listening on the microphone
  emo <name>       push a face to the connected robot
  pan <deg>        push a head turn to the connected robot
  tilt <deg>       push a head nod to the connected robot
  status           show whether a robot is connected
  quit
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
import time

import websockets

from . import config, mouth
from .thinking import RobotBrain
from .ears import Ears, normalize, strip_wake_word
from .eyes import Eyes
from .tracker import Tracker

robot_socket: websockets.ServerConnection | None = None
brain: RobotBrain | None = None  # created in main() once the event loop exists
ears: Ears | None = None
heard: asyncio.Queue[tuple[str, float]] = asyncio.Queue()  # (text, when speech began)
awake_until = 0.0  # while time.time() < this, he's awake: no wake word needed
robot_speak_done = asyncio.Event()  # robot finished playing the last reply
eyes = Eyes()
head_moves: asyncio.Queue[tuple[float | None, float | None, bool]] = asyncio.Queue()
tracker: Tracker | None = None


async def send_to_robot(payload: dict) -> bool:
    if robot_socket is None:
        print("(no robot connected — command not sent)")
        return False
    await robot_socket.send(json.dumps(payload))
    return True


def pick_mic_source() -> None:
    """auto: the robot's mic while it's connected, the Mac's otherwise."""
    if ears is None:
        return
    if config.MIC_SOURCE == "auto":
        source = "robot" if robot_socket is not None else "mac"
    else:
        source = config.MIC_SOURCE
    if source != ears.source:
        ears.set_source(source)
        print(f"listening through the {'robot' if source == 'robot' else 'Mac'} mic")


async def handle_robot(websocket: websockets.ServerConnection) -> None:
    global robot_socket
    peer = websocket.remote_address[0] if websocket.remote_address else "?"
    # Anyone on the WiFi can reach this port, so the first message must be a
    # hello carrying the shared token from server/.env. Anything else is
    # dropped without a reply.
    try:
        first = await asyncio.wait_for(websocket.recv(), timeout=2)
        hello = json.loads(first) if isinstance(first, str) else {}
    except (asyncio.TimeoutError, json.JSONDecodeError, websockets.ConnectionClosed):
        hello = {}
    if not isinstance(hello, dict):
        hello = {}  # "[1]", "42", "null" are valid JSON but not a hello
    expected = os.environ.get("ROBOT_TOKEN", "")
    if not expected:
        print("(refusing robot: set ROBOT_TOKEN in server/.env and firmware/include/secrets.h)")
        await websocket.close(1008)
        return
    if hello.get("type") != "hello" or not secrets.compare_digest(str(hello.get("token", "")), expected):
        print(f"(refused a connection from {peer}: bad or missing token)")
        await websocket.close(1008)
        return
    if robot_socket is not None:
        print(f"(refused a second robot from {peer}: one is already connected)")
        await websocket.close(1013)
        return
    robot_socket = websocket
    print(f"robot connected! (fw {hello.get('fw', '?')}, {peer})")
    pick_mic_source()
    if config.MIC_SOURCE in ("auto", "robot"):
        await send_to_robot({"type": "mic", "on": True})
    await send_to_robot({"type": "stream", "on": True, "fps": config.CAMERA_FPS})
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                kind = message[:1]
                if kind == b"\x01" and ears is not None and len(message) % 2 == 1:
                    ears.push_audio(message[1:])  # 1 type byte + whole 16-bit samples
                elif kind == b"\x02":
                    eyes.push_frame(message[1:])
                continue
            try:
                event = json.loads(message)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "state":
                continue  # heartbeat every 5 s; not worth the console space
            if event.get("type") == "speak_done":
                robot_speak_done.set()
                continue
            if event.get("type") == "temp":
                eyes.temperature = event.get("c")
                continue
            print(f"robot: {event}")
    except websockets.ConnectionClosed:
        pass
    finally:
        # Only clear the slot if it's still ours: when the robot reboots, the
        # new connection can arrive before the old one is noticed as dead.
        if robot_socket is websocket:
            robot_socket = None
            print("robot disconnected")
            pick_mic_source()


async def handle_console_line(line: str) -> bool:
    """Returns False when the server should shut down."""
    line = line.strip()
    if not line:
        return True
    cmd, _, arg = line.partition(" ")
    cmd = cmd.lower()
    arg = arg.strip()

    if cmd == "quit":
        return False
    if cmd == "status":
        print("robot connected" if robot_socket else "no robot connected")
    elif cmd == "emo":
        if arg in config.EMOTIONS:
            await send_to_robot({"type": "emotion", "name": arg})
        else:
            print(f"emotions: {', '.join(config.EMOTIONS)}")
    elif cmd in ("pan", "tilt"):
        try:
            deg = float(arg)
            await send_to_robot({"type": cmd, "deg": deg})
            if tracker is not None:
                tracker.note_pose(**{cmd: deg})
        except ValueError:
            print(f"usage: {cmd} <degrees>")
    elif cmd == "track":
        await set_tracking(arg != "off")
    elif cmd == "ask":
        if not arg:
            print("usage: ask <question>")
            return True
        await converse(arg)
    elif cmd == "listen":
        if ears is None:
            await start_listening()
        else:
            stop_listening()
    elif cmd == "mic":
        await mic_meter()
    elif cmd == "say":
        if arg:
            await say(arg)
        else:
            print("usage: say <text>")
    elif cmd == "volume":
        try:
            await send_to_robot({"type": "volume", "level": float(arg)})
        except ValueError:
            print("usage: volume <0.0-1.0>")
    else:
        print("commands: ask <q> | say <text> | volume <0-1> | listen | mic | emo <name> | pan <deg> | tilt <deg> | status | quit")
    return True


# ── Rocky's abilities (called by the brain, from its worker thread) ──────────

async def look(args: dict) -> tuple[str, bytes | None]:
    """Move the head, wait for it to get there, and grab a fresh frame."""
    pan = tracker.pan if tracker else 0.0
    tilt = tracker.tilt if tracker else 0.0
    d = args.get("direction")
    if d == "left":
        pan = -40.0
    elif d == "right":
        pan = 40.0
    elif d == "down":
        tilt = config.TRACK_TILT_MIN
    elif d == "level":
        tilt = config.TRACK_TILT_MAX
    elif d == "center":
        pan, tilt = 0.0, config.TRACK_TILT_MAX
    if args.get("pan") is not None:
        pan = float(args["pan"])
    if args.get("tilt") is not None:
        tilt = float(args["tilt"])
    pan = max(-config.TRACK_PAN_LIMIT, min(config.TRACK_PAN_LIMIT, pan))
    tilt = max(config.TRACK_TILT_MIN, min(config.TRACK_TILT_MAX, tilt))

    if tracker is not None and tracker.enabled:
        await set_tracking(False, announce=False)  # tracking would drag the head back
    await send_to_robot({"type": "pan", "deg": pan})
    await send_to_robot({"type": "tilt", "deg": tilt})
    if tracker is not None:
        tracker.note_pose(pan=pan, tilt=tilt)
    await asyncio.sleep(1.2)  # servo easing + a frame or two from the new angle
    seq = eyes.frame_seq
    for _ in range(10):
        if eyes.frame_seq != seq:
            break
        await asyncio.sleep(0.1)
    jpeg = eyes.latest()
    where = f"Head is now at pan {pan:.0f} deg ({'left' if pan < -5 else 'right' if pan > 5 else 'center'}), tilt {tilt:.0f} deg ({'down' if tilt < -5 else 'level'})."
    return (where + (" Fresh camera image attached." if jpeg else " No camera image available."), jpeg)


async def set_tracking(on: bool, announce: bool = True) -> tuple[str, bytes | None]:
    if tracker is None:
        return ("no tracker running", None)
    tracker.enabled = on
    if not on and tracker.tracking:
        tracker.tracking = False
        await send_to_robot({"type": "glance", "on": True})
        eyes.tracking_info = {"tracking": False, "pan": tracker.pan, "tilt": tracker.tilt}
    if announce:
        print(f"tracking {'on' if on else 'off'}")
    return ("now following the human's face" if on else "stopped following", None)


def _sync(coro_fn):
    """Wrap an async ability so the brain's worker thread can call it."""
    def run(args: dict):
        return asyncio.run_coroutine_threadsafe(coro_fn(args), main_loop).result(timeout=15)
    return run


main_loop: asyncio.AbstractEventLoop | None = None
ABILITIES = {
    "look": _sync(look),
    "track_face": _sync(lambda args: set_tracking(bool(args.get("on", True)))),
}


def wants_camera(question: str) -> bool:
    """Does the question sound like it's about what Rocky can see?"""
    q = " " + normalize(question) + " "
    return any(f" {w} " in q or (" " in w and w in q) for w in config.CAMERA_WORDS)


async def converse(question: str) -> None:
    """Ask the brain, show the face, and speak the answer."""
    global awake_until
    loop = asyncio.get_running_loop()
    await send_to_robot({"type": "emotion", "name": "thinking"})
    jpeg = eyes.latest() if (config.SEND_CAMERA_TO_BRAIN and wants_camera(question)) else None
    # The SDK call is synchronous — run it off the event loop.
    reply = await loop.run_in_executor(None, brain.ask, question, jpeg)
    print(f"{config.ROBOT_NAME} [{reply.emotion}]: {reply.text}")
    eyes.last_said = reply.text
    await send_to_robot({"type": "emotion", "name": reply.emotion})
    await say(reply.text)
    awake_until = time.time() + config.AWAKE_SECONDS


_tts_checker = None


def check_tts(text: str, pcm: bytes) -> None:
    """Transcribe what the voice model produced and compare it with the text
    it was given. Extra words = the model hallucinated (a laugh, "hello", a
    sound). Runs in a worker thread; prints only when something's off."""
    global _tts_checker
    import re
    from .ears import Transcriber
    if _tts_checker is None:
        _tts_checker = Transcriber("base.en")
    import numpy as np
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    heard = _tts_checker.transcribe(audio)
    words = lambda t: set(re.findall(r"[a-z']+", t.lower()))
    said, got = words(mouth.clean_for_tts(text)), words(heard)
    extra = got - said
    missing = said - got
    # Transcription is imperfect: only shout when several words are foreign.
    if len(extra) >= 3 or (len(extra) >= 2 and len(extra) >= len(got) / 3):
        print(f"  !! TTS CHECK: audio contains words not in the text: {sorted(extra)}")
        print(f"     text : {text}\n     heard: {heard}")
    elif len(missing) >= max(3, len(said) // 2):
        print(f"  !! TTS CHECK: audio is missing much of the text. heard: {heard}")


async def say(text: str) -> bytes:
    """Speak: through the robot's speaker when it's connected, else the Mac.
    Ears are muted meanwhile so Rocky doesn't hear himself."""
    loop = asyncio.get_running_loop()
    if ears is not None:
        ears.muted.set()
    try:
        pcm = await asyncio.wait_for(loop.run_in_executor(None, mouth.synthesize, text), timeout=45)
        if config.DEBUG_TTS_CHECK and pcm:
            loop.run_in_executor(None, check_tts, text, pcm)  # in parallel with playback
        if robot_socket is not None:
            await speak_on_robot(pcm)
        else:
            await asyncio.wait_for(loop.run_in_executor(None, mouth.play, pcm), timeout=45)
        return pcm
    except asyncio.TimeoutError:
        print("(speaking took too long — giving up on this line)")
        return b""
    except Exception as e:  # a TTS hiccup shouldn't kill the server
        print(f"(could not speak: {e})")
        return b""
    finally:
        if ears is not None:
            ears.muted.clear()


async def speak_on_robot(pcm: bytes) -> None:
    """Stream PCM to the robot (docs/protocol.md) and wait until it has played."""
    chunk = 3200  # 100 ms of 16 kHz s16le per frame
    robot_speak_done.clear()
    await send_to_robot({"type": "speak_begin", "bytes": len(pcm)})
    for i in range(0, len(pcm), chunk):
        if robot_socket is None:
            return
        await robot_socket.send(b"\x01" + pcm[i:i + chunk])
    await send_to_robot({"type": "speak_end"})
    seconds = len(pcm) / 32000
    try:
        await asyncio.wait_for(robot_speak_done.wait(), timeout=seconds + 5)
    except asyncio.TimeoutError:
        print("(robot never said it finished speaking)")


# ── Listening ────────────────────────────────────────────────────────────────

async def mic_meter() -> None:
    """Three seconds of live mic level so you can see whether it hears you."""
    import numpy as np
    import sounddevice as sd
    from .ears import BLOCK_SAMPLES, SAMPLE_RATE

    if ears is not None and ears.source == "robot":
        # Robot mic: its frames are already flowing in; just watch the level.
        print("robot mic: talk to the robot for 3 seconds...")
        levels = []
        for _ in range(6):
            await asyncio.sleep(0.5)
            levels.append(ears.level)
            print(f"  level {ears.level:.3f} {'#' * min(50, int(ears.level * 500))}")
        peak = max(levels)
        thr = ears.threshold
        print(f"peak {peak:.3f}  threshold {thr:.3f} (adaptive; min {config.ROBOT_MIC_THRESHOLD})  ->",
              "speech would trigger" if peak > thr else
              "TOO QUIET: raise MIC_GAIN in firmware config.h or lower ROBOT_MIC_THRESHOLD")
        return

    if ears is not None:
        ears.muted.set()
    levels: list[float] = []
    try:
        channels = max(1, int(sd.query_devices(config.MIC_DEVICE, "input")["max_input_channels"]))
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=channels, dtype="float32",
                            blocksize=BLOCK_SAMPLES, device=config.MIC_DEVICE,
                            callback=lambda d, f, t, s: levels.append(
                                float(np.sqrt(np.mean(np.square(d.sum(axis=1))))))) as stream:
            name = sd.query_devices(stream.device)["name"]
            print(f"mic \"{name}\": talk for 3 seconds...")
            for _ in range(6):
                await asyncio.sleep(0.5)
                if levels:
                    bar = "#" * min(50, int(levels[-1] * 500))
                    print(f"  level {levels[-1]:.3f} {bar}")
    except Exception as e:
        print(f"(mic error: {e})")
        return
    finally:
        if ears is not None:
            ears.muted.clear()
    peak = max(levels) if levels else 0.0
    print(f"peak {peak:.3f}  threshold {config.MIC_THRESHOLD}  ->",
          "speech would trigger" if peak > config.MIC_THRESHOLD else
          "TOO QUIET: wrong mic, gain down, or no mic permission")
    print("other inputs:", ", ".join(f"[{i}] {d['name']}" for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0))


async def start_listening() -> None:
    global ears
    loop = asyncio.get_running_loop()
    print(f"loading speech model {config.STT_MODEL} (first run downloads it)...")
    try:
        ears = await loop.run_in_executor(
            None,
            lambda: Ears(lambda text, t0: loop.call_soon_threadsafe(heard.put_nowait, (text, t0))),
        )
        mic = await loop.run_in_executor(None, ears.start)
    except Exception as e:
        ears = None
        print(f"(could not start listening: {e})")
        print("  check: mic plugged in? Terminal allowed to use the microphone in")
        print("  System Settings > Privacy & Security > Microphone? MIC_DEVICE in config.py?")
        return
    print(f"listening on \"{mic}\" — say \"hey {config.ROBOT_NAME}\"")
    pick_mic_source()


def stop_listening() -> None:
    global ears
    if ears is not None:
        ears.stop()
        ears = None
    print("stopped listening")


async def head_loop() -> None:
    """Sends the tracker's head moves to the robot; pauses idle glances while
    a face is being followed and resumes them when it's lost."""
    was_tracking = False
    while True:
        pan, tilt, tracking = await head_moves.get()
        if tracking != was_tracking:
            await send_to_robot({"type": "glance", "on": not tracking})
            print("tracking: face found — head follows" if tracking else "tracking: face lost — idle glances resume")
            was_tracking = tracking
        if pan is not None:
            await send_to_robot({"type": "pan", "deg": pan})
        if tilt is not None:
            await send_to_robot({"type": "tilt", "deg": tilt})
        eyes.tracking_info = {"tracking": tracking, "pan": pan, "tilt": tilt}


async def doze_loop() -> None:
    """When the awake clock runs out, he nods off on his own (sleepy face,
    no announcement). Saying "hey Rocky" wakes him again."""
    was_awake = False
    while True:
        await asyncio.sleep(1)
        awake = time.time() < awake_until
        if was_awake and not awake:
            print(f"({config.ROBOT_NAME} dozed off — say \"hey {config.ROBOT_NAME}\" to wake him)")
            await send_to_robot({"type": "asleep", "on": True})
        was_awake = awake


async def voice_loop() -> None:
    """Turns what the ears hear into conversations."""
    global awake_until
    while True:
        text, started_at = await heard.get()
        woke, question = strip_wake_word(text)
        # Judge the follow-up window by when you STARTED talking, not by when
        # the transcript arrived — long sentences shouldn't time out.
        if not woke and started_at >= awake_until:
            print(f"(heard, ignoring: {text})")
            continue
        print(f"{config.HUMAN_NAME}: {text}")
        eyes.last_heard = text
        awake_until = time.time() + config.AWAKE_SECONDS  # anything you say keeps him up
        norm = normalize(text)
        if any(p in norm for p in config.TRACK_ON_PHRASES) and not any(p in norm for p in config.TRACK_OFF_PHRASES):
            await set_tracking(True)
            print(f"{config.ROBOT_NAME} [happy]: {config.TRACK_ON_LINE}")
            await send_to_robot({"type": "emotion", "name": "happy"})
            await say(config.TRACK_ON_LINE)
            continue
        if any(p in norm for p in config.TRACK_OFF_PHRASES):
            await set_tracking(False)
            print(f"{config.ROBOT_NAME} [neutral]: {config.TRACK_OFF_LINE}")
            await send_to_robot({"type": "emotion", "name": "neutral"})
            await say(config.TRACK_OFF_LINE)
            continue
        if any(p in norm for p in config.SLEEP_PHRASES):
            # "Rocky, sleep": goodnight line, sleepy face, and only "hey Rocky"
            # wakes him. No brain call.
            awake_until = 0.0
            print(f"{config.ROBOT_NAME} [sleepy]: {config.SLEEP_LINE}")
            await send_to_robot({"type": "emotion", "name": "sleepy"})
            await say(config.SLEEP_LINE)
            await send_to_robot({"type": "asleep", "on": True})
            awake_until = 0.0  # say() doesn't touch it, but be explicit
            continue
        if woke:
            # Heard his name: eyes open, perk up to eye level (tilt can't go
            # above 0 on this build — the platform would hit the pan servo).
            await send_to_robot({"type": "asleep", "on": False})
            await send_to_robot({"type": "emotion", "name": "surprised"})
            if tracker is None or not tracker.tracking:
                await send_to_robot({"type": "tilt", "deg": 0})
                if tracker is not None:
                    tracker.note_pose(tilt=0)
        if woke and not question:
            # Just "hey Rocky" — wait for the actual question.
            await say("Question?")
            awake_until = time.time() + config.AWAKE_SECONDS
            continue
        await converse(question)


async def console_loop() -> None:
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:  # EOF
            break
        if not await handle_console_line(line):
            break


async def main() -> None:
    print(f"{config.ROBOT_NAME} brain server — model {config.MODEL}")
    print(f"listening for the robot on ws://0.0.0.0:{config.PORT}")
    eyes.serve(config.LIVE_VIEW_PORT, config.LIVE_VIEW_BIND)
    print(f"live camera view: http://localhost:{config.LIVE_VIEW_PORT}/  (this Mac only)")
    if not os.environ.get("ROBOT_TOKEN"):
        print("WARNING: ROBOT_TOKEN is not set in server/.env — the robot will be refused")
    global tracker, brain, main_loop
    loop = asyncio.get_running_loop()
    main_loop = loop
    brain = RobotBrain(ABILITIES)
    tracker = Tracker(eyes, lambda p, t, on: loop.call_soon_threadsafe(head_moves.put_nowait, (p, t, on)))
    eyes.has_annotator = True
    tracker.start()
    print("face tracking:", "on" if config.TRACKING else "off — say \"Rocky, track me\" or type `track on`")
    print("type `ask <question>` to talk to the brain right now\n")
    async with websockets.serve(handle_robot, "0.0.0.0", config.PORT, max_size=256 * 1024):
        voice_task = asyncio.create_task(voice_loop())
        doze_task = asyncio.create_task(doze_loop())
        head_task = asyncio.create_task(head_loop())
        if config.LISTEN_ON_START:
            await start_listening()
        try:
            await console_loop()
        finally:
            voice_task.cancel()
            doze_task.cancel()
            head_task.cancel()
            if ears is not None:
                stop_listening()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
