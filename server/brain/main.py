"""desk-robot brain server.

Run with:  python -m brain.main   (from the server/ directory, venv active)

Three jobs:
  1. WebSocket server the robot connects to over WiFi (Milestone 2+).
  2. An interactive console so you can talk to the brain and puppet the
     robot from your keyboard right now.
  3. Listening: hears "hey Rocky" on the mic, sends what you say to
     Claude, and speaks the reply through the robot (or the Mac).

A reply is a pipeline, not a wait: the model's words stream in, each
finished sentence goes to the voice as soon as it exists, and the voice's
audio streams to the speaker as it's made. If you start talking again
before Rocky has begun speaking, the reply is dropped and he listens to
the rest of what you're saying, then answers once.

Console commands:
  ask <question>   send a question to the brain, print and speak the reply
  say <text>       speak text (robot speaker if connected, else the Mac)
  volume <0-1>     set the robot's speaker volume
  track on|off     face tracking (head follows you)
  listen           toggle listening on the microphone
  mic              3-second level meter to check the microphone
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
import queue
import secrets
import sys
import threading
import time

import websockets

from . import config, mouth
from .thinking import Interrupted, RobotBrain
from .ears import Ears, normalize, strip_wake_word
from .eyes import Eyes
from .tracker import Tracker

robot_socket: websockets.ServerConnection | None = None
brain: RobotBrain | None = None  # created in main() once the event loop exists
ears: Ears | None = None
# (text, when speech began, when it ended, when the transcript was ready)
heard: asyncio.Queue[tuple[str, float, float, float]] = asyncio.Queue()
speech_started = asyncio.Event()  # the human began a new turn (set by the ears)
awake_until = 0.0  # while time.time() < this, he's awake: no wake word needed
robot_speak_done = asyncio.Event()  # robot finished playing the last reply
eyes = Eyes()
head_moves: asyncio.Queue[tuple[float | None, float | None, bool]] = asyncio.Queue()
tracker: Tracker | None = None

FRAME_BYTES = 3200  # 100 ms of 16 kHz s16le per audio frame to the robot


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
    # Idle glances would wander the head back toward center within seconds;
    # a deliberate look holds until he dozes off (or is told to center).
    await set_head_held(d != "center")
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
    pan_word = "left" if pan < -5 else "right" if pan > 5 else "center"
    if tilt <= config.TRACK_TILT_MIN + 0.5:
        tilt_word = "down, as far as it goes"
    elif tilt >= config.TRACK_TILT_MAX - 0.5:
        tilt_word = "level, as high as it goes"
    else:
        tilt_word = "down" if tilt < -5 else "level"
    where = f"Head is now at pan {pan:.0f} deg ({pan_word}), tilt {tilt:.0f} deg ({tilt_word})."
    return (where + (" Fresh camera image attached." if jpeg else " No camera image available."), jpeg)


head_held = False  # idle glances paused because he was told to look somewhere


async def set_head_held(held: bool) -> None:
    """Pause the firmware's idle glances while a deliberate look is in effect."""
    global head_held
    if held == head_held:
        return
    head_held = held
    if not (tracker is not None and tracker.tracking):  # tracking manages glances itself
        await send_to_robot({"type": "glance", "on": not held})


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


# ── Speaking ─────────────────────────────────────────────────────────────────

class Timeline:
    """Stage times of one reply, measured from the end of the human's speech."""

    ORDER = ("heard", "face", "first sentence", "first audio", "speaking", "done")

    def __init__(self, t0: float) -> None:
        self.t0 = t0
        self.marks: dict[str, float] = {}

    def mark(self, name: str) -> None:
        self.marks.setdefault(name, time.time())

    def report(self) -> None:
        parts = [f"{n} {self.marks[n] - self.t0:.2f}s" for n in self.ORDER if n in self.marks]
        if parts:
            print("  timing (after your last word): " + " · ".join(parts))


class SpokenReply:
    """One reply in flight, as a three-stage pipeline:
    brain thread (model → sentences) → voice thread (Fish → PCM) → the speaker.

    Each stage hands off through a queue, so the first sentence is being
    voiced while the model writes the second, and audio plays while the
    voice is still generating."""

    BREAK = b""  # marks a sentence boundary in the audio queue

    def __init__(self, loop: asyncio.AbstractEventLoop, timeline: Timeline) -> None:
        self.loop = loop
        self.tl = timeline
        self.sentences: queue.Queue[str | None] = queue.Queue()
        self.audio: queue.Queue[bytes | None] = queue.Queue()
        self.cancel = threading.Event()
        self.spoken: list[str] = []
        self.pcm: list[bytes] = []

    @property
    def text(self) -> str:
        return " ".join(self.spoken)

    def think_and_speak(self, question: str, jpeg: bytes | None) -> None:
        threading.Thread(target=self._think, args=(question, jpeg), daemon=True).start()
        threading.Thread(target=self._voice, daemon=True).start()

    def speak_fixed(self, text: str) -> None:
        """A canned line: no brain involved."""
        self.spoken.append(text)
        self.sentences.put(text)
        self.sentences.put(None)
        threading.Thread(target=self._voice, daemon=True).start()

    def _on_emotion(self, name: str) -> None:
        # Called from the brain thread as soon as the reply's emotion is known.
        if self.cancel.is_set():
            return
        self.tl.mark("face")
        asyncio.run_coroutine_threadsafe(send_to_robot({"type": "emotion", "name": name}), self.loop)

    def _think(self, question: str, jpeg: bytes | None) -> None:
        gen = brain.reply(question, jpeg, on_emotion=self._on_emotion, cancelled=self.cancel)
        try:
            for sentence in gen:
                if self.cancel.is_set():
                    break
                if not self.spoken:
                    self.tl.mark("first sentence")
                self.spoken.append(sentence)
                print(f"{config.ROBOT_NAME} [{brain.emotion}]: {sentence}")
                self.sentences.put(sentence)
        except Interrupted:
            pass
        except Exception as e:  # never let a brain hiccup kill the server
            print(f"(brain error: {e})")
        finally:
            gen.close()  # drops the question from his memory if we bailed early
            self.sentences.put(None)

    def _voice(self) -> None:
        try:
            while (sentence := self.sentences.get()) is not None:
                if self.cancel.is_set():
                    continue
                for chunk in mouth.stream(sentence):
                    if self.cancel.is_set():
                        break
                    if not self.pcm:
                        self.tl.mark("first audio")
                    self.pcm.append(chunk)
                    self.audio.put(chunk)
                self.audio.put(self.BREAK)
        except Exception as e:
            print(f"(voice error: {e})")
        finally:
            self.audio.put(None)

    async def _next(self) -> bytes | None:
        return await self.loop.run_in_executor(None, self.audio.get)

    async def play(self, interruptible: bool = True) -> bool:
        """Send the audio to the speaker as it arrives. Until the first audio
        is ready the human can cancel the whole reply by talking again;
        returns False in that case. Once Rocky is speaking the mic is muted
        (his voice would trigger it) and he finishes what he's saying."""
        get = asyncio.ensure_future(self._next())
        while not get.done():
            if interruptible and (speech_started.is_set() or (ears is not None and ears.talking)):
                self._abort()
                await get
                return False
            await asyncio.wait({get}, timeout=0.05)
        first = get.result()
        if first is None:
            return True  # nothing to say
        if ears is not None:
            ears.muted.set()
        try:
            if robot_socket is not None:
                await self._play_robot(first)
            else:
                await self._play_mac(first)
        finally:
            if ears is not None:
                ears.muted.clear()
        self.tl.mark("done")
        return True

    def _abort(self) -> None:
        self.cancel.set()
        brain.abandon()
        self.sentences.put(None)  # wake the voice thread so it can exit
        self.audio.put(None)

    async def _play_robot(self, first: bytes) -> None:
        """Stream PCM to the robot (docs/protocol.md) and wait until it has played."""
        robot_speak_done.clear()
        # bytes 0 = length unknown: the robot starts after 200 ms of buffer.
        await send_to_robot({"type": "speak_begin", "bytes": 0})
        self.tl.mark("speaking")
        buf = bytearray()
        total = 0
        chunk: bytes | None = first
        while chunk is not None:
            buf += chunk
            while len(buf) >= FRAME_BYTES:
                if robot_socket is None:
                    return
                await robot_socket.send(b"\x01" + bytes(buf[:FRAME_BYTES]))
                del buf[:FRAME_BYTES]
                total += FRAME_BYTES
            chunk = await self._next()
        if buf and robot_socket is not None:
            await robot_socket.send(b"\x01" + bytes(buf))
            total += len(buf)
        await send_to_robot({"type": "speak_end"})
        try:
            await asyncio.wait_for(robot_speak_done.wait(), timeout=total / 32000 + 5)
        except asyncio.TimeoutError:
            print("(robot never said it finished speaking)")

    async def _play_mac(self, first: bytes) -> None:
        """No robot: play each sentence on the Mac as soon as it's complete."""
        self.tl.mark("speaking")
        buf = bytearray()
        chunk: bytes | None = first
        while chunk is not None:
            if chunk == self.BREAK:
                if buf:
                    await self.loop.run_in_executor(None, mouth.play, bytes(buf))
                    buf = bytearray()
            else:
                buf += chunk
            chunk = await self._next()
        if buf:
            await self.loop.run_in_executor(None, mouth.play, bytes(buf))


async def converse(question: str, ended_at: float | None = None, heard_at: float | None = None) -> bool:
    """Ask the brain, show the face, and speak the answer as it forms.
    Returns False if the human started talking again before Rocky spoke
    (the reply was dropped and the question is still open)."""
    global awake_until
    loop = asyncio.get_running_loop()
    tl = Timeline(ended_at or time.time())
    if heard_at is not None:
        tl.marks["heard"] = heard_at
    speech_started.clear()
    await send_to_robot({"type": "emotion", "name": "thinking"})
    jpeg = eyes.latest() if (config.SEND_CAMERA_TO_BRAIN and wants_camera(question)) else None
    reply = SpokenReply(loop, tl)
    reply.think_and_speak(question, jpeg)
    try:
        finished = await reply.play()
    except Exception as e:  # a speaker hiccup shouldn't kill the server
        print(f"(could not speak: {e})")
        finished = True
    if not finished:
        print("  (you kept talking — Rocky will hear the rest and answer once)")
        await send_to_robot({"type": "emotion", "name": "neutral"})
        return False
    if reply.text:
        eyes.last_said = reply.text
        if config.DEBUG_TTS_CHECK and reply.pcm:
            loop.run_in_executor(None, check_tts, reply.text, b"".join(reply.pcm))
    awake_until = time.time() + config.AWAKE_SECONDS
    tl.report()
    return True


async def say(text: str) -> bytes:
    """Speak a fixed line: through the robot's speaker when it's connected,
    else the Mac. Ears are muted meanwhile so Rocky doesn't hear himself."""
    reply = SpokenReply(asyncio.get_running_loop(), Timeline(time.time()))
    reply.speak_fixed(text)
    try:
        await reply.play(interruptible=False)
    except Exception as e:
        print(f"(could not speak: {e})")
    return b"".join(reply.pcm)


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
    heard_text = _tts_checker.transcribe(audio)
    words = lambda t: set(re.findall(r"[a-z']+", t.lower()))
    said, got = words(mouth.clean_for_tts(text)), words(heard_text)
    extra = got - said
    missing = said - got
    # Transcription is imperfect: only shout when several words are foreign.
    if len(extra) >= 3 or (len(extra) >= 2 and len(extra) >= len(got) / 3):
        print(f"  !! TTS CHECK: audio contains words not in the text: {sorted(extra)}")
        print(f"     text : {text}\n     heard: {heard_text}")
    elif len(missing) >= max(3, len(said) // 2):
        print(f"  !! TTS CHECK: audio is missing much of the text. heard: {heard_text}")


# ── Listening ────────────────────────────────────────────────────────────────

async def mic_meter() -> None:
    """Three seconds of live mic level and speech probability, so you can see
    whether it hears you."""
    if ears is None:
        print("(not listening — type `listen` first)")
        return
    which = "robot mic" if ears.source == "robot" else f"Mac mic \"{ears.device_name}\""
    print(f"{which}: talk for 3 seconds...")
    peak_level = 0.0
    peak_prob = 0.0
    for _ in range(12):
        await asyncio.sleep(0.25)
        level, prob = ears.level, ears.speech_prob
        peak_level = max(peak_level, level)
        peak_prob = max(peak_prob, prob)
        print(f"  level {level:.3f} {'#' * min(40, int(level * 500)):40s} speech {prob:.2f}")
    print(f"peak level {peak_level:.3f}, peak speech probability {peak_prob:.2f} (needs > {config.VAD_THRESHOLD}) ->",
          "speech detected" if peak_prob > config.VAD_THRESHOLD else
          ("NOT DETECTED: raise MIC_GAIN in firmware config.h, or get closer" if ears.source == "robot" else
           "NOT DETECTED: wrong mic, gain down, or no mic permission"))
    if ears.source == "mac":
        import sounddevice as sd
        print("other inputs:", ", ".join(f"[{i}] {d['name']}" for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0))


async def start_listening() -> None:
    global ears
    loop = asyncio.get_running_loop()
    print(f"loading speech model {config.STT_MODEL} and the turn-taking models (first run downloads them)...")
    try:
        ears = await loop.run_in_executor(
            None,
            lambda: Ears(
                on_utterance=lambda text, t0, t1: loop.call_soon_threadsafe(
                    heard.put_nowait, (text, t0, t1, time.time())
                ),
                on_speech_start=lambda: loop.call_soon_threadsafe(speech_started.set),
            ),
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
            await set_head_held(False)  # idle life resumes; the head may wander again
        was_awake = awake


async def _next_heard() -> tuple[str, float, float, float] | None:
    """Wait for the rest of an interrupted question. Keeps waiting while the
    ears still hear speech; gives up after a few quiet seconds."""
    waited = 0.0
    while True:
        try:
            return await asyncio.wait_for(heard.get(), timeout=0.5)
        except asyncio.TimeoutError:
            waited += 0.5
            hearing = ears is not None and ears.hearing
            if (not hearing and waited >= 4.0) or waited >= 30.0:
                return None


async def voice_loop() -> None:
    """Turns what the ears hear into conversations. A bug in one turn must
    not kill the loop (then nothing you say would get through), so each turn
    is guarded."""
    while True:
        item = await heard.get()
        try:
            await _handle_heard(item)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"(voice loop error, ignoring that turn: {e})")


async def _handle_heard(item: tuple[str, float, float, float]) -> None:
    global awake_until
    text, started_at, ended_at, heard_at = item
    woke, question = strip_wake_word(text)
    # Judge the follow-up window by when you STARTED talking, not by when
    # the transcript arrived — long sentences shouldn't time out.
    if not woke and started_at >= awake_until:
        print(f"(heard, ignoring: {text})")
        return
    print(f"{config.HUMAN_NAME}: {text}")
    eyes.last_heard = text
    awake_until = time.time() + config.AWAKE_SECONDS  # anything you say keeps him up
    norm = normalize(text)
    if any(p in norm for p in config.TRACK_ON_PHRASES) and not any(p in norm for p in config.TRACK_OFF_PHRASES):
        await set_tracking(True)
        print(f"{config.ROBOT_NAME} [happy]: {config.TRACK_ON_LINE}")
        await send_to_robot({"type": "emotion", "name": "happy"})
        await say(config.TRACK_ON_LINE)
        return
    if any(p in norm for p in config.TRACK_OFF_PHRASES):
        await set_tracking(False)
        print(f"{config.ROBOT_NAME} [neutral]: {config.TRACK_OFF_LINE}")
        await send_to_robot({"type": "emotion", "name": "neutral"})
        await say(config.TRACK_OFF_LINE)
        return
    if any(p in norm for p in config.SLEEP_PHRASES):
        # "Rocky, sleep": goodnight line, sleepy face, and only "hey Rocky"
        # wakes him. No brain call.
        awake_until = 0.0
        print(f"{config.ROBOT_NAME} [sleepy]: {config.SLEEP_LINE}")
        await send_to_robot({"type": "emotion", "name": "sleepy"})
        await say(config.SLEEP_LINE)
        await send_to_robot({"type": "asleep", "on": True})
        awake_until = 0.0  # say() doesn't touch it, but be explicit
        return
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
        return
    finished = await converse(question, ended_at, heard_at)
    while not finished:
        # He was cut off while thinking: wait for the rest of the sentence
        # and answer the whole thing once.
        item = await _next_heard()
        if item is None:
            print("  (didn't catch the rest — answering what I heard)")
            finished = await converse(question)
            continue
        text, started_at, ended_at, heard_at = item
        _, more = strip_wake_word(text)
        print(f"{config.HUMAN_NAME}: {text}")
        question = f"{question} {more}".strip()
        eyes.last_heard = question
        awake_until = time.time() + config.AWAKE_SECONDS
        finished = await converse(question, ended_at, heard_at)


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
