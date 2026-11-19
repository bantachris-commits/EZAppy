"""SQLite history: raw samples plus one row per day."""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import date, datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    ts      INTEGER PRIMARY KEY,   -- unix seconds
    p1      REAL, p2 REAL,         -- watts per channel
    e_today REAL,                  -- kWh reported by inverter since start-up
    e_life  REAL                   -- lifetime kWh
);
CREATE TABLE IF NOT EXISTS daily (
    day        TEXT PRIMARY KEY,   -- local date YYYY-MM-DD
    start_life REAL,               -- lifetime kWh at first sample of the day
    last_life  REAL,               -- lifetime kWh at latest sample
    max_today  REAL,               -- highest e_today seen that day
    peak_w     REAL                -- highest total power seen that day
);
"""


class Store:
    def __init__(self, path: str, keep_days: int = 90):
        self.keep_days = keep_days
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(SCHEMA)

    def add_sample(self, ts: int, p1: float, p2: float, e_today: float, e_life: float) -> None:
        day = datetime.fromtimestamp(ts).date().isoformat()
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?)", (ts, p1, p2, e_today, e_life)
            )
            self._db.execute(
                """INSERT INTO daily VALUES (?,?,?,?,?)
                   ON CONFLICT(day) DO UPDATE SET
                     last_life = excluded.last_life,
                     max_today = MAX(max_today, excluded.max_today),
                     peak_w    = MAX(peak_w, excluded.peak_w)""",
                (day, e_life, e_life, e_today, p1 + p2),
            )
            self._db.execute(
                "DELETE FROM samples WHERE ts < ?", (int(time.time()) - self.keep_days * 86400,)
            )

    def samples_since(self, since_ts: int) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT ts, p1, p2 FROM samples WHERE ts >= ? ORDER BY ts", (since_ts,)
            ).fetchall()
        return [{"ts": ts, "p1": p1, "p2": p2, "power": p1 + p2} for ts, p1, p2 in rows]

    def daily(self, days: int = 30) -> list[dict]:
        cutoff = date.fromordinal(date.today().toordinal() - days + 1).isoformat()
        with self._lock:
            rows = self._db.execute(
                "SELECT day, start_life, last_life, max_today, peak_w FROM daily "
                "WHERE day >= ? ORDER BY day",
                (cutoff,),
            ).fetchall()
        # Lifetime delta survives mid-day inverter restarts; the inverter's own
        # daily counter covers days where monitoring started late. Take the larger.
        return [
            {"day": d, "energy": round(max(last - start, mx), 3), "peak_w": peak}
            for d, start, last, mx, peak in rows
        ]
