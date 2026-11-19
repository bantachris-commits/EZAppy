"""A fake EZ1 for demos and tests: `python -m ez1monitor.simulator [port]`.

Power follows a sun curve between 06:00 and 20:00 local time, with a little noise.
"""

from __future__ import annotations

import json
import math
import random
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class SimState:
    def __init__(self):
        self.max_power = 800
        self.on = True
        self.e = [0.0, 0.0]
        self.te = [412.3, 409.8]
        self.last = time.time()

    def powers(self) -> list[float]:
        now = datetime.now()
        hour = now.hour + now.minute / 60
        sun = max(0.0, math.sin(math.pi * (hour - 6) / 14)) if 6 <= hour <= 20 else 0.0
        if not self.on:
            return [0.0, 0.0]
        cap = self.max_power / 2
        return [round(min(cap, 400 * sun * random.uniform(0.9, 1.0)), 1) for _ in range(2)]

    def tick(self) -> list[float]:
        p = self.powers()
        dt_h = (time.time() - self.last) / 3600
        self.last = time.time()
        for i in range(2):
            self.e[i] += p[i] * dt_h / 1000
            self.te[i] += p[i] * dt_h / 1000
        return p


def backfill(store, state: SimState, days: int = 14, step: int = 300) -> None:
    """Fill a Store with `days` of fake history ending now (for --demo)."""
    rng = random.Random(42)
    now = int(time.time())
    life = 300.0
    t = now - days * 86400
    day, e_today, cloud = None, 0.0, 1.0
    while t < now:
        dt = datetime.fromtimestamp(t)
        if dt.date() != day:
            day, e_today, cloud = dt.date(), 0.0, rng.uniform(0.35, 1.0)
        hour = dt.hour + dt.minute / 60
        sun = max(0.0, math.sin(math.pi * (hour - 6) / 14)) if 6 <= hour <= 20 else 0.0
        if sun > 0:
            p = [round(400 * sun * cloud * rng.uniform(0.85, 1.0), 1) for _ in range(2)]
            e_today += sum(p) * step / 3600 / 1000
            life += sum(p) * step / 3600 / 1000
            store.add_sample(t, p[0], p[1], e_today, life)
        t += step
    state.te = [life / 2, life / 2]
    state.e = [e_today / 2, e_today / 2]


def make_server(host: str = "127.0.0.1", port: int = 8050, state: SimState | None = None) -> ThreadingHTTPServer:
    st = state or SimState()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            url = urlparse(self.path)
            q = parse_qs(url.query)
            path = url.path.strip("/")
            if path == "getDeviceInfo":
                data = {"deviceId": "E07000000001", "devVer": "EZ1 1.7.0", "ssid": "HomeWiFi",
                        "ipAddr": "192.168.1.50", "minPower": "30", "maxPower": "800"}
            elif path == "getOutputData":
                p = st.tick()
                data = {"p1": p[0], "e1": round(st.e[0], 3), "te1": round(st.te[0], 3),
                        "p2": p[1], "e2": round(st.e[1], 3), "te2": round(st.te[1], 3)}
            elif path == "getMaxPower":
                data = {"maxPower": str(st.max_power)}
            elif path == "setMaxPower" and "p" in q:
                st.max_power = max(30, min(800, int(q["p"][0])))
                data = {"maxPower": str(st.max_power)}
            elif path == "getAlarm":
                data = {"og": "0", "isce1": "0", "isce2": "0", "oe": "0"}
            elif path == "getOnOff":
                data = {"status": "0" if st.on else "1"}
            elif path == "setOnOff" and "status" in q:
                st.on = q["status"][0] == "0"
                data = {"status": "0" if st.on else "1"}
            else:
                self.send_error(404)
                return
            body = json.dumps({"data": data, "message": "SUCCESS", "deviceId": "E07000000001"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer((host, port), H)
    srv.sim_state = st
    return srv


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8050
    print(f"Simulated EZ1 on http://127.0.0.1:{port}")
    make_server("127.0.0.1", port).serve_forever()
