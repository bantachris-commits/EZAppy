"""Background poller + small HTTP server for the dashboard."""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .ez1 import EZ1Client, EZ1Error
from .store import Store

log = logging.getLogger("ez1monitor")
STATIC = Path(__file__).parent / "static"


class Poller(threading.Thread):
    """Polls the inverter and records samples. Slows down while it's offline."""

    def __init__(self, client: EZ1Client, store: Store, interval: float = 15, offline_interval: float = 60):
        super().__init__(daemon=True)
        self.client = client
        self.store = store
        self.interval = interval
        self.offline_interval = offline_interval
        self._info: dict | None = None
        self._halt = threading.Event()
        self.state: dict = {"online": False, "error": "Waiting for first reading", "last": None}

    def poll_once(self) -> bool:
        try:
            snap = self.client.snapshot(self._info)
        except EZ1Error as exc:
            self._info = None  # re-read device info after reconnect
            if self.state.get("online"):
                log.warning("Inverter went offline: %s", exc)
            self.state = {
                "online": False,
                "error": str(exc),
                "checked": datetime.now().astimezone().isoformat(timespec="seconds"),
                "last": self.state.get("last"),
            }
            return False
        self._info = snap["device"]
        out = snap["output"]
        self.store.add_sample(snap["epoch"], out["p1"], out["p2"], out["energy_today"], out["energy_lifetime"])
        if not self.state.get("online"):
            log.info("Inverter online: %s (%s)", snap["device"]["device_id"], snap["device"]["firmware"])
        self.state = {"online": True, "error": None, "checked": snap["time"], "last": snap}
        return True

    def run(self) -> None:
        while not self._halt.is_set():
            ok = self.poll_once()
            self._halt.wait(self.interval if ok else self.offline_interval)

    def stop(self) -> None:
        self._halt.set()


def make_handler(poller: Poller, store: Store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # keep the console quiet
            log.debug(fmt, *args)

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj) -> None:
            self._send(200, json.dumps(obj).encode(), "application/json")

        def do_GET(self):
            url = urlparse(self.path)
            q = parse_qs(url.query)
            arg = lambda k, d: int(q.get(k, [d])[0])  # noqa: E731
            try:
                if url.path in ("/", "/index.html"):
                    self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
                elif url.path == "/api/status":
                    self._json(poller.state)
                elif url.path == "/api/history":
                    hours = max(1, min(arg("hours", 24), 24 * 31))
                    self._json(store.samples_since(int(time.time()) - hours * 3600))
                elif url.path == "/api/daily":
                    self._json(store.daily(max(1, min(arg("days", 30), 365))))
                else:
                    self._send(404, b"Not found", "text/plain")
            except ValueError:
                self._send(400, b"Bad request", "text/plain")

    return Handler


def serve(client: EZ1Client, store: Store, bind: str, port: int, interval: float) -> None:
    poller = Poller(client, store, interval=interval)
    poller.start()
    httpd = ThreadingHTTPServer((bind, port), make_handler(poller, store))
    shown = "localhost" if bind in ("127.0.0.1", "0.0.0.0") else bind
    log.info("Monitoring EZ1 at %s — dashboard on http://%s:%d", client.base_url, shown, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        poller.stop()
        httpd.server_close()
