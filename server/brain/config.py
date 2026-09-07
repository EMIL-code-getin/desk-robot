"""Central knobs for the desk-robot brain."""

import os
from pathlib import Path

# ── Secrets ──────────────────────────────────────────────────────────────────
# API keys live in server/.env (git-ignored; see .env.example), one KEY=VALUE
# per line. Anything already exported in the shell wins over the file.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if _ENV_FILE.is_file():
    for _line in _ENV_FILE.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))

# The robot's name — the wake word (M4) will be "hey <name>".
ROBOT_NAME = "Rocky"

# Your name — Rocky calls you this.
HUMAN_NAME = "Casey"

# Language model for the personality, by OpenRouter model id (openrouter.ai
# /models). Needs OPENROUTER_API_KEY in your shell. One key, any model:
#   "anthropic/claude-haiku-4.5"     best at staying in character, ~$1-4/month
#   "google/gemini-2.5-flash-lite"   cheapest that still sounds like Rocky
#   "openai/gpt-4.1-mini"            middle ground
MODEL = "anthropic/claude-haiku-4.5"

# WebSocket port the robot connects to.
PORT = 8765

# Text-to-speech (M3). Rocky's voice comes from Fish Audio (fish.audio):
# open the voice's page on the site, copy the model/reference ID from the
# URL into TTS_VOICE_ID, and export FISH_AUDIO_API_KEY in your shell.
TTS_PROVIDER = "fish"
TTS_VOICE_ID = "6dd07916890445e59c5f019ad0fc7879"  # 32-char hex ID from the voice page URL on fish.audio
TTS_FALLBACK_VOICE = "Fred"  # macOS `say` voice used until Fish Audio is set up
# Fish Audio generation settings. Lower = steadier, fewer hallucinated
# sounds/laughs/extra words (a known quirk of generated speech); higher =
# more expressive. Fish's defaults are 0.7 / 0.7.
TTS_TEMPERATURE = 0.4
TTS_TOP_P = 0.6
# Fish's output is quiet (peaks around 0.2-0.7 of full scale) and streams to
# the speaker as it's generated, so per-clip normalizing isn't possible. This
# gain is applied through a soft limiter: quiet lines get the full boost,
# loud peaks are eased into full scale rather than clipped. Prefer the
# robot's `volume` for everyday loudness; raise this only if short lines
# still come out too quiet.
TTS_GAIN = 2.5
# Diagnostics: save each spoken clip (server/debug/tts/…, keeps the last 30)
# and, if DEBUG_TTS_CHECK, transcribe it afterwards to flag audio that doesn't
# match the text — i.e. the voice model made something up. The check runs a
# second speech model right after every reply, which slows the next
# transcription if you answer quickly; leave it off unless the voice misbehaves.
DEBUG_SAVE_TTS = True
DEBUG_TTS_CHECK = False

# Listening (M4). Prototype on the Mac's mic now; the robot's mic takes over
# once its audio streams in over WiFi (M3).
LISTEN_ON_START = True
WAKE_PHRASES = [  # what speech-to-text tends to hear for "hey Rocky"
    "hey rocky",
    "hey rocket",
    "hey rocking",
    "hi rocky",
    "a rocky",
    "hey ricky",
]
STT_MODEL = "base.en"    # faster-whisper model: base.en ~0.3 s per utterance on an M2,
                         # small.en hears a little better but takes ~1 s
STT_THREADS = 8          # CPU threads for transcription (0 = library default of 4)
STT_PROMPT = f"Hey {ROBOT_NAME}. {ROBOT_NAME} is a robot."  # name hint for the model
MIC_SOURCE = "auto"      # "robot" = the robot's mic, "mac" = MIC_DEVICE below,
                         # "auto" = robot when it's connected, else the Mac
MIC_DEVICE = "Scarlett Solo USB"  # None = system default. List devices: python -m sounddevice
# Speech detection (server/brain/turn.py). A Silero VAD model decides whether
# each 32 ms chunk is speech (VAD_THRESHOLD, 0..1: lower = more sensitive), so
# the loudness of a particular mic no longer matters. When you pause for
# TURN_PAUSE_SECONDS the Smart Turn model listens to the whole sentence and
# decides whether you sound finished (probability above TURN_THRESHOLD ->
# Rocky answers now). If it thinks you're mid-thought it keeps listening,
# re-checking every TURN_RECHECK_SECONDS, and gives up waiting after
# TURN_MAX_SILENCE seconds of quiet. If Rocky keeps cutting you off, raise
# TURN_THRESHOLD; if he waits too long after you finish, lower it.
VAD_THRESHOLD = 0.5
TURN_PAUSE_SECONDS = 0.2
TURN_RECHECK_SECONDS = 0.6
TURN_MAX_SILENCE = 2.5
TURN_THRESHOLD = 0.5
# If you start talking again while Rocky is still thinking (before he speaks),
# speech that lasts this long cancels his reply and he listens to the rest.
CANCEL_MIN_SPEECH = 0.3
DEBUG_SAVE_UTTERANCE = ""  # set to "debug/last_utterance.wav" to keep the last thing heard, for mic tuning
AWAKE_SECONDS = 60.0     # after "hey Rocky" he stays awake; each thing you say
                         # resets this clock, and when it runs out he dozes off
SLEEP_PHRASES = [        # any of these puts him to sleep until the next "hey Rocky"
    "rocky sleep",
    "rocky go to sleep",
    "go to sleep",
    "goodnight",
    "good night",
    "stop listening",
]
SLEEP_LINE = "I sleep. You watch. Wake me when you find bug."  # said as he goes to sleep

# Emotions the firmware knows how to display (see firmware/src/face.cpp).
EMOTIONS = [
    "neutral",
    "happy",
    "sad",
    "angry",
    "surprised",
    "sleepy",
    "thinking",
]

# Camera (M5). The robot streams small JPEGs while connected; the live view
# is at http://localhost:<LIVE_VIEW_PORT>/ on the Mac.
CAMERA_FPS = 10
LIVE_VIEW_PORT = 8766
LIVE_VIEW_BIND = "127.0.0.1"  # this Mac only. "0.0.0.0" would show the camera to the whole LAN.
SEND_CAMERA_TO_BRAIN = True  # let Rocky see the camera when a question is about seeing
# A frame is attached only when the question sounds visual (any of these
# words), so "what's 9 times 16" doesn't come with a photo that distracts him.
# He can always use his `look` ability to get a fresh picture on his own.
CAMERA_WORDS = [
    "see", "seeing", "look", "looking", "watch", "camera", "picture", "photo",
    "image", "view", "show", "holding", "wearing", "color", "colour", "this",
    "that", "here", "there", "room", "desk", "behind", "front", "left", "right",
    "read", "screen", "whiteboard", "what am i", "who is", "who's", "how many",
    "describe", "notice",
]

# Face tracking (M5): the head follows the biggest face in the picture.
# Off until you ask ("Rocky, track me"); phrases below switch it without a
# brain call, and Rocky can also switch it himself when asked in other words.
TRACKING = False
TRACK_ON_PHRASES = ["track me", "follow me", "watch me", "keep your eyes on me", "look at me"]
TRACK_OFF_PHRASES = ["stop tracking", "stop following", "stop watching", "stop looking at me"]
TRACK_ON_LINE = "Yes yes yes. Eyes on Casey."
TRACK_OFF_LINE = "Okay. Eyes free."
TRACK_HFOV = 62.0          # camera field of view, degrees (OV2640 stock lens)
TRACK_VFOV = 48.0
TRACK_GAIN = 0.5           # fraction of the error corrected per frame (lower = calmer)
TRACK_DEADBAND = 0.10      # ignore errors smaller than this fraction of half-frame
TRACK_PAN_SIGN = 1         # flip to -1 if the head turns AWAY from you
TRACK_TILT_SIGN = 1        # flip to -1 if it nods the wrong way
TRACK_PAN_LIMIT = 60.0     # must match PAN_MIN/MAX_DEG in firmware config.h
TRACK_TILT_MIN = -30.0     # must match TILT_MIN/MAX_DEG in firmware config.h
TRACK_TILT_MAX = 0.0
TRACK_LOST_SECONDS = 4.0   # no face this long → idle glances resume

# Reply length: the prompt asks for this many sentences at most, and the
# server cuts anything past it before it's spoken (keeps voice cost down).
REPLY_MAX_SENTENCES = 3

# How many conversation turns to remember before forgetting the oldest.
MAX_HISTORY_TURNS = 20
