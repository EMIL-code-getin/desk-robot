"""Eyes: the robot's camera stream, and a live-view page for the browser.

The robot sends one JPEG per binary frame (type byte 0x02). We keep only the
newest. A tiny HTTP server (standard library, its own thread) serves:

  /          a page with the live picture and a status line
  /stream    multipart MJPEG — the newest frame, pushed as it changes
  /frame     the newest frame as a plain JPEG
  /status    JSON: fps, frame age, chip temperature, last transcript
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config


class Eyes:
    def __init__(self) -> None:
        self.jpeg: bytes = b""          # newest raw frame from the robot
        self.frame_at = 0.0
        self.frame_seq = 0
        self.display: bytes = b""       # what the browser shows (annotated if a tracker runs)
        self.display_seq = 0
        self.has_annotator = False       # set by the tracker; then it publishes frames
        self.tracking_info: dict = {}
        self.frames = 0
        self._fps_window: list[float] = []
        self.temperature: float | None = None
        self.last_heard = ""
        self.last_said = ""
        self._cond = threading.Condition()

    # ── robot → server ──────────────────────────────────────────────────────
    def push_frame(self, jpeg: bytes) -> None:
        now = time.time()
        with self._cond:
            self.jpeg = jpeg
            self.frame_at = now
            self.frame_seq += 1
            self.frames += 1
            self._fps_window.append(now)
            self._fps_window = [t for t in self._fps_window if now - t < 2.0]
            if not self.has_annotator:
                self.display = jpeg
                self.display_seq = self.frame_seq
            self._cond.notify_all()

    def publish(self, jpeg: bytes) -> None:
        """A frame for the browser (the tracker's annotated copy)."""
        if not jpeg:
            return
        with self._cond:
            self.display = jpeg
            self.display_seq += 1
            self._cond.notify_all()

    def wait_for_display(self, seen_seq: int, timeout: float = 1.0) -> int:
        with self._cond:
            self._cond.wait_for(lambda: self.display_seq != seen_seq, timeout=timeout)
            return self.display_seq

    def latest(self, max_age: float = 2.0) -> bytes | None:
        """The newest frame if it's recent enough to be worth showing Claude."""
        if self.jpeg and time.time() - self.frame_at <= max_age:
            return self.jpeg
        return None

    def fps(self) -> float:
        return len(self._fps_window) / 2.0

    def wait_for_new(self, seen_seq: int, timeout: float = 1.0) -> int:
        with self._cond:
            self._cond.wait_for(lambda: self.frame_seq != seen_seq, timeout=timeout)
            return self.frame_seq

    # ── browser ─────────────────────────────────────────────────────────────
    def serve(self, port: int, bind: str = "127.0.0.1") -> None:
        eyes = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "desk-robot"  # don't advertise the Python version
            sys_version = ""

            def log_message(self, *args) -> None:  # keep the console quiet
                pass

            def do_GET(self) -> None:
                # A malicious web page can point its own domain at 127.0.0.1
                # (DNS rebinding) and read a localhost server. Only answer
                # requests addressed to us by a local name.
                host = (self.headers.get("Host") or "").split(":")[0].strip("[]").lower()
                if host not in ("localhost", "127.0.0.1", "::1", bind.lower()):
                    self._reply(403, "text/plain", b"forbidden")
                    return
                if self.path == "/":
                    body = PAGE.replace("{name}", config.ROBOT_NAME).encode()
                    self._reply(200, "text/html; charset=utf-8", body)
                elif self.path == "/frame":
                    if eyes.jpeg:
                        self._reply(200, "image/jpeg", eyes.jpeg)
                    else:
                        self._reply(503, "text/plain", b"no frame yet")
                elif self.path == "/status":
                    st = {
                        "fps": round(eyes.fps(), 1),
                        "frame_age_s": round(time.time() - eyes.frame_at, 1) if eyes.frame_at else None,
                        "frames": eyes.frames,
                        "temperature_c": eyes.temperature,
                        "last_heard": eyes.last_heard,
                        "last_said": eyes.last_said,
                        **eyes.tracking_info,
                    }
                    self._reply(200, "application/json", json.dumps(st).encode())
                elif self.path == "/stream":
                    self._stream()
                else:
                    self._reply(404, "text/plain", b"not found")

            def _reply(self, code: int, ctype: str, body: bytes) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _stream(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                seq = -1
                try:
                    while True:
                        seq = eyes.wait_for_display(seq, timeout=1.0)
                        frame = eyes.display
                        if not frame:
                            continue
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                        self.wfile.write(frame)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

        server = ThreadingHTTPServer((bind, port), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()


PAGE = """<!doctype html>
<meta charset="utf-8">
<title>{name} live view</title>
<style>
  body { margin: 0; background: #111; color: #ddd; font: 14px system-ui, sans-serif; }
  .wrap { max-width: 960px; margin: 0 auto; padding: 16px; }
  img { width: 100%; image-rendering: auto; background: #000; border-radius: 8px; }
  .row { display: flex; gap: 24px; flex-wrap: wrap; margin-top: 10px; color: #9ab; }
  .say { margin-top: 8px; color: #eee; }
  .say span { color: #7c9; }
</style>
<div class="wrap">
  <img id="v" src="/stream" alt="waiting for the robot's camera...">
  <div class="row">
    <div>fps <b id="fps">–</b></div>
    <div>frame age <b id="age">–</b> s</div>
    <div>chip <b id="temp">–</b> °C</div>
    <div>tracking <b id="track">–</b></div>
    <div>head pan <b id="pan">–</b>° tilt <b id="tilt">–</b>°</div>
  </div>
  <div class="say">heard: <span id="heard"></span></div>
  <div class="say">{name}: <span id="said"></span></div>
</div>
<script>
  async function tick() {
    try {
      const s = await (await fetch('/status')).json();
      fps.textContent = s.fps; age.textContent = s.frame_age_s ?? '–';
      temp.textContent = s.temperature_c ?? '–';
      track.textContent = s.tracking === undefined ? '–' : (s.tracking ? 'face' : 'no face');
      pan.textContent = s.pan ?? '–'; tilt.textContent = s.tilt ?? '–';
      heard.textContent = s.last_heard; said.textContent = s.last_said;
    } catch (e) {}
    setTimeout(tick, 1000);
  }
  tick();
</script>
"""
