"""Mouth: turn Rocky's words into sound.

Two voices:
  * Fish Audio (Rocky's real voice) when TTS_VOICE_ID and FISH_AUDIO_API_KEY
    are set. Plain HTTPS POST asking for raw 16 kHz PCM. The response body
    streams, so the first audio arrives ~0.3 s in, long before the sentence
    is finished, and is passed straight on to the speaker.
  * macOS `say` as the fallback so the loop is audible before that's set up.

`stream(text)` yields 16 kHz mono s16le PCM chunks — the exact format the
robot's speaker expects (docs/protocol.md) — as they're produced.
`synthesize()` is the same joined into one buffer; `play()` plays a buffer
on the Mac.
"""

from __future__ import annotations

import io
import json
import os
import re
import ssl
import subprocess
import tempfile
import time
import urllib.request
import wave
from collections.abc import Iterator

import certifi

import numpy as np

from . import config

SAMPLE_RATE = 16_000
FISH_TTS_URL = "https://api.fish.audio/v1/tts"


def fish_available() -> bool:
    return bool(config.TTS_VOICE_ID and os.environ.get("FISH_AUDIO_API_KEY"))


_MARKUP = re.compile(r"[*_`#~<>\[\]{}|\\]")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")


def clean_for_tts(text: str) -> str:
    """What the voice model gets: plain spoken words. Markdown marks, emoji
    and runs of punctuation tend to make generated speech do odd things."""
    text = _EMOJI.sub("", _MARKUP.sub("", text))
    text = re.sub(r"([!?.,])\1+", r"\1", text)      # "!!!" -> "!"
    text = re.sub(r"\.{2,}", ".", text)              # "..." -> "."
    text = re.sub(r"\s+", " ", text).strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _fish_stream(text: str) -> Iterator[bytes]:
    """Raw 16 kHz PCM from Fish Audio, yielded as the server produces it."""
    body = json.dumps(
        {
            "text": text,
            "reference_id": config.TTS_VOICE_ID,
            "format": "pcm",          # headerless s16le at sample_rate: nothing to parse
            "sample_rate": SAMPLE_RATE,
            "latency": "balanced",    # a little faster to the first byte than "normal"
            "temperature": config.TTS_TEMPERATURE,
            "top_p": config.TTS_TOP_P,
        }
    ).encode()
    req = urllib.request.Request(
        FISH_TTS_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {os.environ['FISH_AUDIO_API_KEY']}",
            "Content-Type": "application/json",
        },
    )
    # python.org builds of Python on macOS don't see the system root certs;
    # certifi's bundle (already installed with the openai package) does.
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        carry = b""  # a chunk boundary can split a 16-bit sample in half
        while chunk := resp.read(4096):
            chunk = carry + chunk
            if len(chunk) % 2:
                chunk, carry = chunk[:-1], chunk[-1:]
            else:
                carry = b""
            if chunk:
                yield chunk


class Leveler:
    """Streaming automatic gain: holds the voice near a steady loudness.

    Fish's level wanders from sentence to sentence and within one, and audio
    streams to the speaker as it's made, so it can't be normalized after the
    fact. Each chunk (~130 ms) gets a loudness reading; a smoothed estimate
    follows it upward over ~0.3 s and downward over ~1.5 s, ignoring
    near-silence so gaps don't pump up the noise. The gain steers toward
    TTS_LEVEL / estimate, capped at TTS_MAX_GAIN, and is ramped across each
    chunk so nothing clicks. The shape inside a chunk (syllables) is kept.
    Use one Leveler per reply so its sentences match each other."""

    GATE = 0.004        # RMS below this is a gap, not a quiet word
    ATTACK = 0.5        # per chunk: louder than expected → follow fast
    RELEASE = 0.1       # per chunk: quieter than expected → follow slowly
    SQUEEZE = 0.35      # how far each chunk is pulled toward the running level
                        # (0 = only sentence-scale leveling, 1 = flatten every chunk)
    CEILING = 0.95      # never let a chunk's peak exceed this: no clipping

    def __init__(self) -> None:
        self.env = 0.0      # loudness estimate; 0 = nothing heard yet
        self.gain = 1.0

    def process(self, pcm: bytes) -> bytes:
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if not len(x):
            return pcm
        rms = float(np.sqrt(np.mean(x * x)))
        if rms > self.GATE:
            if self.env == 0.0:
                self.env = rms                                  # first sound: trust it
            elif rms > self.env:
                self.env += self.ATTACK * (rms - self.env)
            else:
                self.env += self.RELEASE * (rms - self.env)
        if self.env and rms > self.GATE:
            # Judge this chunk by a blend of the running level and its own
            # level: loud bits come down a little, quiet words come up a little.
            judged = self.env * (rms / self.env) ** self.SQUEEZE
            target = min(config.TTS_MAX_GAIN, max(0.5, config.TTS_LEVEL / judged))
        else:
            target = self.gain  # a gap: hold the gain where it is
        peak = float(np.abs(x).max())
        if peak > 0:
            target = min(target, self.CEILING / peak)
        y = x * np.linspace(self.gain, target, len(x), dtype=np.float32)
        self.gain = target
        top = float(np.abs(y).max())
        if top > self.CEILING:  # the ramp started above the cap: trim the whole chunk
            y *= self.CEILING / top
        return (y * 32767).astype(np.int16).tobytes()


def _wav_to_pcm16k(wav_bytes: bytes) -> bytes:
    """Any WAV → 16 kHz mono s16le, whatever rate/channels/width it came in."""
    with wave.open(io.BytesIO(wav_bytes)) as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        frames = w.readframes(w.getnframes())
    if width == 2:
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768
    elif width == 1:
        samples = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128) / 128
    elif width == 4:
        samples = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2**31
    else:
        raise ValueError(f"unsupported WAV sample width {width}")
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE:
        n_out = int(len(samples) * SAMPLE_RATE / rate)
        x_old = np.linspace(0, 1, len(samples), endpoint=False)
        x_new = np.linspace(0, 1, n_out, endpoint=False)
        samples = np.interp(x_new, x_old, samples).astype(np.float32)
    return (np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes()


def _synthesize_say(text: str) -> bytes:
    """macOS built-in voice, written straight to 16 kHz s16le WAV."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    try:
        # Text goes in on stdin, never as an argument: `say` would treat a
        # reply starting with "-" as options ("-f /etc/hosts" reads a file).
        subprocess.run(
            ["say", "-v", config.TTS_FALLBACK_VOICE, "-o", path, "--data-format=LEI16@16000"],
            input=text.encode(),
            check=True,
        )
        with open(path, "rb") as f:
            wav = f.read()
    finally:
        os.unlink(path)
    return wav[44:]  # skip the 44-byte WAV header; the rest is raw PCM


def stream(text: str, leveler: Leveler | None = None) -> Iterator[bytes]:
    """Rocky's words as 16 kHz mono s16le PCM chunks, yielded as they're made.
    Fish Audio when it's set up and reachable, else the Mac's own voice (all
    at once). Loudness is steadied by `leveler` (a fresh one if none is
    given). A saved copy goes to debug/tts/ when DEBUG_SAVE_TTS is on."""
    text = clean_for_tts(text)
    if not text:
        return
    leveler = leveler or Leveler()
    parts: list[bytes] = []
    complete = False
    try:
        chunks: Iterator[bytes] | None = None
        first = b""
        if fish_available():
            try:
                chunks = _fish_stream(text)
                first = next(chunks, b"")
            except Exception as e:  # network, auth, bad voice id... still speak
                print(f"(fish audio failed, using Mac voice: {e})")
                chunks = None
        if chunks is None:
            first = _synthesize_say(text)
        if first:
            first = leveler.process(first)
            parts.append(first)
            yield first
        if chunks is not None:
            try:
                for chunk in chunks:
                    chunk = leveler.process(chunk)
                    parts.append(chunk)
                    yield chunk
            except Exception as e:  # dropped mid-stream: say what we have
                print(f"(fish audio stream cut short: {e})")
        complete = True
    finally:
        if complete and parts and config.DEBUG_SAVE_TTS:
            _save_clip(b"".join(parts), text)


def synthesize(text: str) -> bytes:
    """Rocky's reply as one 16 kHz mono signed 16-bit little-endian PCM buffer."""
    return b"".join(stream(text))


def _save_clip(pcm: bytes, text: str) -> None:
    """Keep recent clips on disk so a weird one can be inspected."""
    try:
        d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "debug", "tts")
        os.makedirs(d, exist_ok=True)
        stamp = time.strftime("%H%M%S")
        path = os.path.join(d, f"{stamp}.wav")
        with wave.open(path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SAMPLE_RATE); w.writeframes(pcm)
        with open(path[:-4] + ".txt", "w") as f:
            f.write(text + "\n")
        old = sorted(f for f in os.listdir(d) if f.endswith(".wav"))[:-30]
        for f in old:
            for ext in (".wav", ".txt"):
                try: os.unlink(os.path.join(d, f[:-4] + ext))
                except OSError: pass
    except OSError:
        pass


def normalize(pcm: bytes, peak: float = 0.95) -> bytes:
    """Scale so the loudest sample hits `peak` of full scale. Used for the
    Mac fallback voice, which arrives all at once."""
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    top = float(np.abs(samples).max()) if len(samples) else 0.0
    if top < 1:
        return pcm
    return np.clip(samples * (peak * 32767 / top), -32768, 32767).astype(np.int16).tobytes()


def play(pcm: bytes) -> None:
    """Play PCM on the Mac's default output. Blocks until done.

    Uses macOS's own player rather than sounddevice: opening an output stream
    while the mic stream is running trips CoreAudio ("cannot do in current
    context") and can hang. afplay is a separate process, so it can't."""
    if not pcm:
        return
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    try:
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm)
        subprocess.run(["afplay", path], check=False, timeout=60)
    finally:
        os.unlink(path)


def speak(text: str) -> bytes:
    """Synthesize and play on the Mac; returns the PCM for the robot too."""
    pcm = synthesize(text)
    play(pcm)
    return pcm
