"""Tests for build_usb.py against a local stand-in for download.kiwix.org.

    python -m pytest offline-usb/tests      (or: python -m unittest discover offline-usb/tests)
"""
import hashlib
import http.server
import io
import json
import sys
import tarfile
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_usb as b  # noqa: E402


class Mirror:
    """Serves a dict {path: bytes} with directory listings, HEAD, Range and
    .sha256 side files, like a Kiwix mirror. `cut` truncates the next GET of a
    path to simulate a dropped connection."""

    def __init__(self, files: dict[str, bytes], sha=True):
        self.files, self.sha, self.cut, self.ranges = files, sha, {}, []
        mirror = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _body(self):
                p = self.path
                if p.endswith("/"):
                    names = sorted({k[len(p):].split("/")[0] for k in mirror.files if k.startswith(p)})
                    html = "".join(f'<a href="{n}">{n}</a>\n' for n in names)
                    return 200, html.encode()
                if mirror.sha and p.endswith(".sha256") and p[:-7] in mirror.files:
                    return 200, (hashlib.sha256(mirror.files[p[:-7]]).hexdigest() + "  x\n").encode()
                if p in mirror.files:
                    return 200, mirror.files[p]
                return 404, b"nope"

            def _send(self, head):
                code, body = self._body()
                start = 0
                rng = self.headers.get("Range")
                if code == 200 and rng and not self.path.endswith("/"):
                    mirror.ranges.append((self.path, rng))
                    start = int(rng.split("=")[1].split("-")[0])
                    if start >= len(body):
                        self.send_response(416)
                        self.end_headers()
                        return
                    code = 206
                payload = body[start:]
                self.send_response(code)
                self.send_header("Content-Length", str(len(payload)))
                if code == 206:
                    self.send_header("Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}")
                self.end_headers()
                if head:
                    return
                if self.path in mirror.cut:
                    payload = payload[: mirror.cut.pop(self.path)]
                    self.wfile.write(payload)
                    self.wfile.flush()
                    self.connection.shutdown(2)
                    return
                self.wfile.write(payload)

            def do_GET(self):
                self._send(False)

            def do_HEAD(self):
                self._send(True)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


def tar_with(name: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        info = tarfile.TarInfo(f"kiwix-tools_x/{name}")
        info.size, info.mode = len(content), 0o755
        t.addfile(info, io.BytesIO(content))
    return buf.getvalue()


ITEMS = [
    b.Item("a", "sv", "lite", "wikipedia", ["wikipedia_sv_all_mini"], "A"),
    b.Item("b", "sv", "standard", "wikipedia", ["wikipedia_sv_all_nopic"], "B", not_in=["full"]),
    b.Item("c", "en", "lite", "other", ["zimgit-water_en"], "C"),
    b.Item("d", "en", "full", "gutenberg", ["gutenberg_en_all"], "D", optional=True),
    b.Item("e", "sv", "lite", "wikivoyage", ["wikivoyage_sv_all_maxi", "wikivoyage_sv_all_nopic"], "E"),
]
TIERS = ["lite", "standard", "full"]


class Selection(unittest.TestCase):
    def ids(self, *a, **k):
        return [i.id for i in b.select_items(ITEMS, TIERS, *a, **k)]

    def test_tier_and_language(self):
        self.assertEqual(self.ids("lite", ["sv"]), ["a", "e"])
        self.assertEqual(self.ids("standard", ["sv", "en"]), ["a", "b", "c", "e"])

    def test_bigger_edition_replaces_smaller(self):
        self.assertEqual(self.ids("full", ["sv"]), ["a", "e"])

    def test_optional_only_on_request_and_exclude_wins(self):
        self.assertNotIn("d", self.ids("full", ["en"]))
        self.assertIn("d", self.ids("lite", ["sv"], include={"d"}))
        self.assertNotIn("a", self.ids("lite", ["sv"], include={"a"}, exclude={"a"}))

    def test_unknown_id_is_an_error(self):
        with self.assertRaises(SystemExit):
            self.ids("lite", ["sv"], include={"nope"})

    def test_real_catalog_loads_and_every_tier_has_swedish_wikipedia(self):
        cat = b.load_catalog()
        for tier in cat["tiers"]:
            ids = [i.id for i in b.select_items(cat["items"], cat["tiers"], tier, ["sv"])]
            self.assertEqual(sum(i.startswith("wikipedia-sv") for i in ids), 1, tier)


class Resolving(unittest.TestCase):
    def test_newest_date_wins(self):
        names = ["wikipedia_sv_all_mini_2025-11.zim", "wikipedia_sv_all_mini_2026-03.zim",
                 "wikipedia_sv_all_mini_2026-03.zim.torrent", "wikipedia_sv_all_minix_2027-01.zim"]
        self.assertEqual(b.newest_zim(names, "wikipedia_sv_all_mini"), "wikipedia_sv_all_mini_2026-03.zim")

    def test_kiwix_tools_version_sort(self):
        names = ["kiwix-tools_linux-x86_64-3.7.0.tar.gz", "kiwix-tools_linux-x86_64-3.10.0.tar.gz",
                 "kiwix-tools_linux-x86_64-3.7.0-2.tar.gz", "kiwix-tools_linux-aarch64-3.11.0.tar.gz"]
        self.assertEqual(b.newest_kiwix_tools(names, "linux-x86_64", "tar.gz"),
                         "kiwix-tools_linux-x86_64-3.10.0.tar.gz")

    def test_fallback_prefix_and_missing(self):
        m = Mirror({"/zim/wikivoyage/wikivoyage_sv_all_nopic_2026-01.zim": b"x"})
        try:
            with redirect_stdout(io.StringIO()):
                found, missing = b.resolve([ITEMS[4], ITEMS[0]], m.url)
        finally:
            m.close()
        self.assertEqual([r.file for r in found], ["wikivoyage_sv_all_nopic_2026-01.zim"])
        self.assertEqual(found[0].size, 1)
        self.assertEqual([i.id for i in missing], ["a"])


class Downloading(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = bytes(range(256)) * 20000           # ~5 MB, several chunks

    def run_dl(self, m, path="/f.zim", **kw):
        with redirect_stdout(io.StringIO()):
            b.download(m.url + path, self.tmp / "f.zim", len(self.data), log=lambda *a: None, **kw)

    def test_fresh_download_checks_hash(self):
        m = Mirror({"/f.zim": self.data})
        try:
            self.run_dl(m)
        finally:
            m.close()
        self.assertEqual((self.tmp / "f.zim").read_bytes(), self.data)
        self.assertFalse((self.tmp / "f.zim.part").exists())

    def test_resumes_partial_file(self):
        (self.tmp / "f.zim.part").write_bytes(self.data[:1_000_000])
        m = Mirror({"/f.zim": self.data})
        try:
            self.run_dl(m)
        finally:
            m.close()
        self.assertEqual((self.tmp / "f.zim").read_bytes(), self.data)
        self.assertEqual(m.ranges, [("/f.zim", "bytes=1000000-")])

    def test_dropped_connection_is_retried_from_where_it_stopped(self):
        m = Mirror({"/f.zim": self.data})
        m.cut["/f.zim"] = 2_000_000
        b.time.sleep, real = (lambda s: None), b.time.sleep
        try:
            self.run_dl(m)
        finally:
            b.time.sleep = real
            m.close()
        self.assertEqual((self.tmp / "f.zim").read_bytes(), self.data)
        self.assertTrue(m.ranges and m.ranges[0][1].startswith("bytes=") and m.ranges[0][1] != "bytes=0-")

    def test_bad_hash_removes_file(self):
        m = Mirror({"/f.zim": self.data})
        (self.tmp / "f.zim.part").write_bytes(b"\xff" * 1000)   # corrupt start
        try:
            with self.assertRaises(RuntimeError):
                self.run_dl(m)
        finally:
            m.close()
        self.assertFalse((self.tmp / "f.zim").exists())
        self.assertFalse((self.tmp / "f.zim.part").exists())

    def test_without_published_hash_still_downloads(self):
        m = Mirror({"/f.zim": self.data}, sha=False)
        try:
            self.run_dl(m)
        finally:
            m.close()
        self.assertEqual((self.tmp / "f.zim").read_bytes(), self.data)


class EndToEnd(unittest.TestCase):
    def test_build_update_and_portal_index(self):
        tmp = Path(tempfile.mkdtemp())
        cat = {"tiers": TIERS, "items": [vars(i) for i in ITEMS[:3]],
               "kiwix_tools": {"linux-x86_64": {"folder": "linux-x64", "ext": "tar.gz"}}}
        (tmp / "catalog.json").write_text(json.dumps(cat))
        files = {
            "/zim/wikipedia/wikipedia_sv_all_mini_2026-01.zim": b"old-mini",
            "/zim/wikipedia/wikipedia_sv_all_mini_2026-04.zim": b"new-mini",
            "/zim/other/zimgit-water_en_2025-02.zim": b"water",
            "/release/kiwix-tools/kiwix-tools_linux-x86_64-3.8.0.tar.gz": tar_with("kiwix-serve", b"#!bin"),
        }
        m = Mirror(files)
        drive = tmp / "drive"
        drive.mkdir()
        (drive / "library").mkdir()
        (drive / "library" / "wikipedia_sv_all_mini_2026-01.zim").write_bytes(b"old-mini")
        (drive / "library" / "mitt-eget.zim").write_bytes(b"mine")
        args = ["--target", str(drive), "--catalog", str(tmp / "catalog.json"),
                "--mirror", m.url, "--tier", "lite", "--lang", "sv,en", "--yes"]
        try:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(b.main(args + ["--dry-run"]), 0)
                self.assertFalse((drive / "START-LINUX.sh").exists())
                self.assertEqual(b.main(args), 0)
                again = io.StringIO()
            with redirect_stdout(again):
                self.assertEqual(b.main(args), 0)          # second run: nothing to fetch
        finally:
            m.close()

        lib = sorted(p.name for p in (drive / "library").iterdir())
        self.assertEqual(lib, ["mitt-eget.zim", "wikipedia_sv_all_mini_2026-04.zim", "zimgit-water_en_2025-02.zim"])
        self.assertEqual((drive / "kiwix" / "linux-x64" / "kiwix-serve").read_bytes(), b"#!bin")
        for f in ["START-WINDOWS.bat", "START-MAC.command", "START-LINUX.sh", "portal/index.html", "egna-filer"]:
            self.assertTrue((drive / f).exists(), f)
        js = (drive / "portal" / "bibliotek.js").read_text(encoding="utf-8")
        books = json.loads(js[js.index("["): js.rindex("]") + 1])
        self.assertEqual({x["book"] for x in books},
                         {"mitt-eget", "wikipedia_sv_all_mini_2026-04", "zimgit-water_en_2025-02"})
        self.assertIn("finns redan", again.getvalue())
        self.assertEqual(json.loads((drive / "manifest.json").read_text())["failed"], [])


if __name__ == "__main__":
    unittest.main()
