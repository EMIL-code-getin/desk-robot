"""Thinking: sends a question (and the newest camera frame) to the language
model via OpenRouter and returns what Rocky should say and feel.

OpenRouter (openrouter.ai) fronts many models behind one key using the
OpenAI-style chat API, so the model is just a string in config.py.

Rocky has two real abilities the model can call (tool use): `look` moves
the head and comes back with a fresh camera frame from the new angle, and
`track_face` starts/stops following the human. main.py supplies the
functions that actually do those things.
"""

from __future__ import annotations

import base64
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass

import openai

from . import config
from .personality import SYSTEM_PROMPT

_EMOTION_TAG = re.compile(r"^\s*\[(\w+)\]\s*", re.S)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def limit_sentences(text: str, n: int) -> str:
    """Keep the first n sentences. A trailing fragment with no end mark counts
    as a sentence too."""
    parts = [p for p in _SENTENCE_END.split(text.strip()) if p]
    return " ".join(parts[:n]) if n > 0 else text

# An action returns (text for the model, optional fresh camera JPEG).
Action = Callable[[dict], tuple[str, bytes | None]]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "look",
            "description": (
                "Move your head to look somewhere. Use it whenever you are asked to "
                "look left/right/down/up/around, or need to see something outside "
                "the current picture. You get a fresh camera image afterwards; "
                "describe only what that image shows. Up is as high as 'level': "
                "your neck cannot tilt above eye level."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["left", "right", "down", "level", "center"],
                        "description": "A named direction (center = straight ahead, level)",
                    },
                    "pan": {"type": "number", "description": "Absolute pan in degrees: -60 (your left) to 60 (your right)"},
                    "tilt": {"type": "number", "description": "Absolute tilt in degrees: -30 (down) to 0 (level)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "track_face",
            "description": "Start or stop following the human's face with your head.",
            "parameters": {
                "type": "object",
                "properties": {"on": {"type": "boolean"}},
                "required": ["on"],
            },
        },
    },
]


@dataclass
class Reply:
    text: str
    emotion: str


def _image_part(jpeg: bytes) -> dict:
    data = base64.standard_b64encode(jpeg).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}}


class RobotBrain:
    def __init__(self, actions: dict[str, Action] | None = None) -> None:
        self.client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY", "missing"),
            default_headers={"X-Title": "desk-robot"},  # shows up in OpenRouter's usage page
        )
        self.history: list[dict] = []
        self.actions = actions or {}

    def ask(self, question: str, jpeg: bytes | None = None) -> Reply:
        content: list[dict] = [{"type": "text", "text": question}]
        if jpeg is not None:
            content.append(_image_part(jpeg))
        self.history.append({"role": "user", "content": content})
        mark = len(self.history) - 1

        try:
            reply = self._converse()
        except openai.APIConnectionError:
            del self.history[mark:]
            return Reply("Brain cannot reach internet. Bad bad bad.", "sad")
        except openai.AuthenticationError:
            del self.history[mark:]
            return Reply("Brain has no key. Set OPENROUTER_API_KEY, human.", "sad")
        except openai.APIStatusError as e:
            del self.history[mark:]
            return Reply(f"Ow. Brain hurts. API error {e.status_code}.", "sad")

        self._strip_images()
        self._trim_history()
        return reply

    def _converse(self) -> Reply:
        """One question, possibly several model calls if it uses its abilities."""
        nudged = False
        for _ in range(5):
            response = self.client.chat.completions.create(
                model=config.MODEL,
                max_tokens=200,  # backstop; the sentence limit does the real work
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, *self.history],
                tools=TOOLS if self.actions else openai.NOT_GIVEN,
            )
            msg = response.choices[0].message
            calls = msg.tool_calls or []
            if not calls:
                raw = (msg.content or "").strip()
                if not raw and not nudged:
                    # Some models go quiet right after using an ability. Ask once.
                    nudged = True
                    self.history.append({"role": "user", "content": "(Tell your human what you just did, in one short line.)"})
                    continue
                if nudged and self.history and self.history[-1].get("role") == "user":
                    self.history.pop()  # don't keep the nudge in the transcript
                if not raw:
                    return Reply("Hmm. Words did not come. Ask again.", "thinking")
                reply = self._parse(raw)
                full = reply.text
                reply.text = limit_sentences(full, config.REPLY_MAX_SENTENCES)
                if reply.text != full:
                    print(f"  (trimmed reply to {config.REPLY_MAX_SENTENCES} sentences)")
                # Remember what was actually said, so he can't refer back to
                # the part that got cut.
                self.history.append({"role": "assistant", "content": f"[{reply.emotion}] {reply.text}"})
                return reply

            # He decided to do something: run it, tell him what happened.
            self.history.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": c.id, "type": "function",
                     "function": {"name": c.function.name, "arguments": c.function.arguments}}
                    for c in calls
                ],
            })
            fresh: bytes | None = None
            for c in calls:
                try:
                    args = json.loads(c.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                action = self.actions.get(c.function.name)
                if action is None:
                    text = f"unknown ability {c.function.name}"
                else:
                    try:
                        text, img = action(args)
                    except Exception as e:  # the robot didn't cooperate; say so
                        text, img = f"could not do that: {e}", None
                    if img:
                        fresh = img
                print(f"  [{c.function.name} {args} -> {text}]")
                self.history.append({"role": "tool", "tool_call_id": c.id, "content": text})
            if fresh is not None:
                self.history.append({
                    "role": "user",
                    "content": [{"type": "text", "text": "Camera view after moving:"}, _image_part(fresh)],
                })
        return Reply("Too many things at once. Ask again, human.", "thinking")

    def _parse(self, raw: str) -> Reply:
        emotion = "neutral"
        m = _EMOTION_TAG.match(raw)
        if m:
            candidate = m.group(1).lower()
            if candidate in config.EMOTIONS:
                emotion = candidate
            raw = _EMOTION_TAG.sub("", raw, count=1)
        return Reply(raw.strip(), emotion)

    def _strip_images(self) -> None:
        """Replace old camera frames with a note. Keeping every image in the
        history would make each later question cost far more."""
        for m in self.history:
            if m.get("role") == "user" and isinstance(m.get("content"), list):
                parts = [p for p in m["content"] if p.get("type") == "text"]
                if len(parts) != len(m["content"]):
                    parts.append({"type": "text", "text": "(a camera image was attached here)"})
                m["content"] = parts

    def _trim_history(self) -> None:
        max_msgs = config.MAX_HISTORY_TURNS * 2
        if len(self.history) > max_msgs:
            cut = len(self.history) - max_msgs
            # Never start the history on a tool result: back up to a user turn.
            while cut < len(self.history) and self.history[cut].get("role") != "user":
                cut += 1
            del self.history[:cut]
