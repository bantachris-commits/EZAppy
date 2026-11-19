"""Client for the APsystems EZ1 microinverter local API.

The EZ1 exposes a small HTTP/JSON API on port 8050 once "Local Mode" is
enabled in the AP EasyPower phone app (Settings -> Local Mode -> Continuous).
Every response looks like {"data": {...}, "message": "SUCCESS", "deviceId": "..."}.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime


class EZ1Error(Exception):
    """The inverter could not be reached or returned an error."""


def _num(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class EZ1Client:
    def __init__(self, host: str, port: int = 8050, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _get(self, path: str) -> dict:
        url = f"{self.base_url}/{path}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise EZ1Error(f"{path}: {exc}") from exc
        if payload.get("message") != "SUCCESS":
            raise EZ1Error(f"{path}: device replied {payload.get('message')!r}")
        return payload.get("data") or {}

    # --- raw endpoints -------------------------------------------------
    def device_info(self) -> dict:
        d = self._get("getDeviceInfo")
        return {
            "device_id": d.get("deviceId", ""),
            "firmware": d.get("devVer", ""),
            "ssid": d.get("ssid", ""),
            "ip": d.get("ipAddr", ""),
            "min_power": _num(d.get("minPower")),
            "max_power": _num(d.get("maxPower")),
        }

    def output_data(self) -> dict:
        d = self._get("getOutputData")
        p1, p2 = _num(d.get("p1")), _num(d.get("p2"))
        e1, e2 = _num(d.get("e1")), _num(d.get("e2"))
        te1, te2 = _num(d.get("te1")), _num(d.get("te2"))
        return {
            "p1": p1, "p2": p2, "power": p1 + p2,
            # e1/e2: kWh since the inverter last started (i.e. since sunrise)
            "e1": e1, "e2": e2, "energy_today": e1 + e2,
            "te1": te1, "te2": te2, "energy_lifetime": te1 + te2,
        }

    def max_power(self) -> float:
        return _num(self._get("getMaxPower").get("maxPower"))

    def alarms(self) -> dict:
        d = self._get("getAlarm")
        flag = lambda k: str(d.get(k, "0")) == "1"  # noqa: E731
        return {
            "off_grid": flag("og"),
            "dc1_short_circuit": flag("isce1"),
            "dc2_short_circuit": flag("isce2"),
            "output_fault": flag("oe"),
        }

    def is_on(self) -> bool:
        # status "0" = producing (on), "1" = switched off
        return str(self._get("getOnOff").get("status", "0")) == "0"

    # --- combined reading ---------------------------------------------
    def snapshot(self, device_info: dict | None = None) -> dict:
        """One full reading. Pass cached device_info to skip that request."""
        info = device_info or self.device_info()
        out = self.output_data()
        return {
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "epoch": int(time.time()),
            "online": True,
            "device": info,
            "output": out,
            "max_power": self.max_power(),
            "on": self.is_on(),
            "alarms": self.alarms(),
        }
