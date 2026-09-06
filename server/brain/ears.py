"""Ears: listen on a microphone, cut the sound into utterances, turn each one
into text.

Two possible microphones feed the same pipeline: the Mac's (sounddevice
stream) or the robot's PDM mic, whose frames arrive over the WebSocket and
are handed in through push_audio(). `source` picks which one is live.

Pipeline:  mic blocks → Segmenter (energy-based voice activity) → Transcriber
(faster-whisper, local, no cloud) → on_utterance(text)
"""

from __future__ import annotations

import queue
import re
import threading
import time
from collections import deque
from collections.abc import Callable

import numpy as np

from . import config

SAMPLE_RATE = 16_000
BLOCK_SECONDS = 0.03  # 30 ms per block
BLOCK_SAMPLES = int(SAMPLE_RATE * BLOCK_SECONDS)


class HighPass:
    """One-pole high-pass (~120 Hz). The PDM mic puts out a DC offset and a lot
    of sub-150 Hz rumble that swamps the noise floor; speech doesn't live there."""

    def __init__(self, cutoff_hz: float = 120.0) -> None:
        self.a = 1.0 / (1.0 + 2.0 * np.pi * cutoff_hz / SAMPLE_RATE)
        self.prev_x = 0.0
        self.prev_y = 0.0

    def process(self, block: np.ndarray) -> np.ndarray:
        out = np.empty_like(block)
        px, py, a = self.prev_x, self.prev_y, self.a
        for i, x in enumerate(block):
            py = a * (py + x - px)
            px = x
            out[i] = py
        self.prev_x, self.prev_y = px, py
        return out


class Segmenter:
    """Feed 30 ms float32 blocks in; get whole utterances (numpy arrays) out.

    Speech starts when a block is louder than the threshold, and ends after
    `end_silence` seconds of quiet. A short pre-roll is kept so the first
    syllable isn't clipped. The threshold adapts: it tracks the room's noise
    floor while nobody is talking and sits MIC_NOISE_RATIO above it, but
    never below `threshold` (the per-mic minimum).
    """

    def __init__(
        self,
        threshold: float = config.MIC_THRESHOLD,
        pre_roll: float = 0.3,
        end_silence: float = 0.9,
        min_length: float = 0.4,
        max_length: float = 15.0,
    ) -> None:
        self.threshold = threshold      # minimum
        self.floor = threshold / config.MIC_NOISE_RATIO  # tracked noise level
        self.pre_roll: deque[np.ndarray] = deque(maxlen=int(pre_roll / BLOCK_SECONDS))
        self.end_blocks = int(end_silence / BLOCK_SECONDS)
        self.min_blocks = int(min_length / BLOCK_SECONDS)
        self.max_blocks = int(max_length / BLOCK_SECONDS)
        self.current: list[np.ndarray] = []
        self.quiet_run = 0
        self.speaking = False
        self.started_at = 0.0  # wall-clock time the current utterance began

    @property
    def effective_threshold(self) -> float:
        return max(self.threshold, self.floor * config.MIC_NOISE_RATIO)

    def push(self, block: np.ndarray) -> np.ndarray | None:
        rms = float(np.sqrt(np.mean(block * block)))
        loud = rms > self.effective_threshold
        if not self.speaking:
            # Track the noise floor slowly, only from quiet blocks.
            if rms < self.floor * 2.0 or rms < self.threshold:
                self.floor = 0.97 * self.floor + 0.03 * rms
            self.pre_roll.append(block)
            if loud:
                self.speaking = True
                self.started_at = time.time()
                self.current = list(self.pre_roll)
                self.quiet_run = 0
            return None

        self.current.append(block)
        self.quiet_run = 0 if loud else self.quiet_run + 1
        if self.quiet_run >= self.end_blocks or len(self.current) >= self.max_blocks:
            utterance = self.current
            self.speaking = False
            self.current = []
            self.pre_roll.clear()
            if len(utterance) - self.quiet_run < self.min_blocks:
                return None  # a click or a cough, not words
            return np.concatenate(utterance)
        return None


class Transcriber:
    """Local speech-to-text. The first run downloads the model (~150 MB for
    base.en) into ~/.cache; after that it's offline."""

    def __init__(self, model_name: str = config.STT_MODEL) -> None:
        from faster_whisper import WhisperModel  # slow import, keep it lazy

        self.model = WhisperModel(model_name, device="cpu", compute_type="int8")

    def transcribe(self, audio: np.ndarray) -> str:
        segments, _ = self.model.transcribe(
            audio,
            language="en",
            beam_size=1,
            vad_filter=True,
            # Tells the model the name to expect; without this "Rocky" comes
            # out as "right" / "righty" about half the time.
            initial_prompt=config.STT_PROMPT,
        )
        return " ".join(s.text.strip() for s in segments).strip()


_WAKE_CLEAN = re.compile(r"[^a-z' ]+")


def normalize(text: str) -> str:
    return " ".join(_WAKE_CLEAN.sub(" ", text.lower()).split())


def _wake_pattern() -> re.Pattern:
    # "hey rocky" -> matches "Hey, Rocky!" etc.: any punctuation/space between
    # the words, case-insensitive, and swallows the punctuation after it.
    alts = "|".join(r"\W+".join(map(re.escape, p.split())) for p in config.WAKE_PHRASES)
    return re.compile(rf"\b(?:{alts})\b[\s,.!?:;-]*", re.IGNORECASE)


_WAKE_RE = _wake_pattern()


def strip_wake_word(text: str) -> tuple[bool, str]:
    """('Hey Rocky, what's 9 times 16?') -> (True, "what's 9 times 16?").
    The question keeps its digits, punctuation and case — the brain needs
    them. Returns (False, text) when no wake phrase is present."""
    m = _WAKE_RE.search(text)
    if m:
        return True, text[m.end():].strip()
    return False, text.strip()


def _save_wav(audio: np.ndarray, path: str) -> None:
    """Keep the last utterance on disk so mic quality can be inspected."""
    import os
    import wave

    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    except OSError:
        pass


class Ears:
    """Owns the microphone stream and a worker thread. Calls
    on_utterance(text, started_at) from the worker thread for every chunk of
    speech heard; started_at is when the person began talking."""

    def __init__(
        self,
        on_utterance: Callable[[str, float], None],
        device: int | str | None = config.MIC_DEVICE,
    ) -> None:
        self.on_utterance = on_utterance
        self.device = device
        self.muted = threading.Event()  # set while Rocky is talking (no echo cancel)
        self.source = "mac"             # "mac" or "robot": whose audio is live
        self.level = 0.0                # RMS of the latest live block (for `mic`)
        self._blocks: queue.Queue[np.ndarray | None] = queue.Queue()
        self._stream = None
        self._worker: threading.Thread | None = None
        self._segmenter = Segmenter()
        self._highpass = HighPass()
        self.transcriber = Transcriber()

    def set_source(self, source: str) -> None:
        """Switch between the Mac mic and the robot mic (thresholds differ)."""
        self.source = source
        self._segmenter.threshold = (
            config.ROBOT_MIC_THRESHOLD if source == "robot" else config.MIC_THRESHOLD
        )
        self._segmenter.floor = self._segmenter.threshold / config.MIC_NOISE_RATIO

    @property
    def threshold(self) -> float:
        return self._segmenter.effective_threshold

    def push_audio(self, pcm16: bytes) -> None:
        """Robot mic frame (16 kHz mono s16le) from the WebSocket."""
        if self.source != "robot" or self.muted.is_set():
            return
        block = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        block = self._highpass.process(block)
        self.level = float(np.sqrt(np.mean(block * block)))
        self._blocks.put(block)

    def start(self) -> str:
        import sounddevice as sd

        # Open every input the device has (a Scarlett has two) and mix them,
        # so it doesn't matter which jack the mic is plugged into.
        channels = max(1, int(sd.query_devices(self.device, "input")["max_input_channels"]))
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=channels,
            dtype="float32",
            blocksize=BLOCK_SAMPLES,
            device=self.device,
            callback=self._on_audio,
        )
        self._stream.start()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()
        return sd.query_devices(self._stream.device)["name"]

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._blocks.put(None)

    def _on_audio(self, indata, frames, time_info, status) -> None:
        if self.source == "mac" and not self.muted.is_set():
            block = np.clip(indata.sum(axis=1), -1.0, 1.0)
            self.level = float(np.sqrt(np.mean(block * block)))
            self._blocks.put(block)

    def _run(self) -> None:
        segmenter = self._segmenter
        while True:
            block = self._blocks.get()
            if block is None:
                return
            utterance = segmenter.push(block)
            if utterance is None:
                continue
            # Bring quiet speech up to a healthy level for the model.
            peak = float(np.abs(utterance).max())
            if peak > 0.001:
                utterance = utterance * min(0.9 / peak, 20.0)
            if config.DEBUG_SAVE_UTTERANCE:
                _save_wav(utterance, config.DEBUG_SAVE_UTTERANCE)
            text = self.transcriber.transcribe(utterance)
            if text:
                self.on_utterance(text, segmenter.started_at)
