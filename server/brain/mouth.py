"""Mouth: turn Rocky's words into sound.

Two voices:
  * Fish Audio (Rocky's real voice) when TTS_VOICE_ID and FISH_AUDIO_API_KEY
    are set. Plain HTTPS POST; we ask for WAV so the format is self-describing,
    then convert to 16 kHz mono PCM.
  * macOS `say` as the fallback so the loop is audible before that's set up.

`synthesize()` returns 16 kHz mono s16le PCM — the exact format the robot's
speaker expects (docs/protocol.md) — so the same bytes play on the Mac now
and stream to the robot in M3. `speak()` plays them on the Mac.
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


def _synthesize_fish(text: str) -> bytes:
    body = json.dumps(
        {
            "text": text,
            "reference_id": config.TTS_VOICE_ID,
            "format": "wav",
            "sample_rate": SAMPLE_RATE,
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
        return _wav_to_pcm16k(resp.read())


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


def synthesize(text: str) -> bytes:
    """Rocky's reply as 16 kHz mono signed 16-bit little-endian PCM."""
    text = clean_for_tts(text)
    if not text:
        return b""
    pcm = None
    if fish_available():
        try:
            pcm = normalize(_synthesize_fish(text))
        except Exception as e:  # network, auth, bad voice id... still speak
            print(f"(fish audio failed, using Mac voice: {e})")
    if pcm is None:
        pcm = normalize(_synthesize_say(text))
    if config.DEBUG_SAVE_TTS:
        _save_clip(pcm, text)
    return pcm


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
        print(f"  (clip saved: debug/tts/{stamp}.wav)")
    except OSError:
        pass


def normalize(pcm: bytes, peak: float = 0.95) -> bytes:
    """Scale so the loudest sample hits `peak` of full scale. TTS output is
    often conservative; the little speaker wants all the range it can get."""
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
