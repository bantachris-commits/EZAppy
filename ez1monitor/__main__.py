"""python -m ez1monitor --inverter 192.168.1.50"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading

from .ez1 import EZ1Client, EZ1Error
from .server import serve
from .store import Store


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ez1monitor", description="Desktop dashboard for an APsystems EZ1 inverter")
    p.add_argument("--inverter", default=os.environ.get("EZ1_HOST"),
                   help="IP address of the EZ1 (or set EZ1_HOST). Find it in the AP EasyPower app under Local Mode.")
    p.add_argument("--inverter-port", type=int, default=8050)
    p.add_argument("--port", type=int, default=8080, help="dashboard port (default 8080)")
    p.add_argument("--bind", default="127.0.0.1",
                   help="address to listen on; use 0.0.0.0 to view from other devices on your LAN")
    p.add_argument("--interval", type=float, default=15, help="seconds between readings (default 15)")
    p.add_argument("--db", default="ez1-history.sqlite3", help="history database file")
    p.add_argument("--scan", nargs="*", metavar="NETWORK",
                   help="search the network for EZ1 inverters and exit (optionally give e.g. 192.168.1.0/24)")
    p.add_argument("--check", action="store_true", help="read the inverter once, print it, and exit")
    p.add_argument("--demo", action="store_true", help="run against a built-in simulated inverter")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    store = None
    if a.demo:
        from .simulator import SimState, backfill, make_server
        state = SimState()
        store = Store(":memory:")
        backfill(store, state)
        sim = make_server("127.0.0.1", 0, state)
        threading.Thread(target=sim.serve_forever, daemon=True).start()
        a.inverter, a.inverter_port = "127.0.0.1", sim.server_address[1]
    if a.scan is not None or not a.inverter:
        from .scan import local_networks, scan
        nets = a.scan or [str(n) for n in local_networks()]
        if not nets:
            p.error("couldn't work out your network; pass one, e.g. --scan 192.168.1.0/24")
        print(f"Scanning {', '.join(nets)} for EZ1 inverters on port {a.inverter_port}...", file=sys.stderr)
        found = scan(nets, a.inverter_port)
        for d in found:
            print(f"  {d['host']}  {d['device_id']}  {d['firmware']}  (Wi-Fi: {d['ssid']})", file=sys.stderr)
        if not found:
            print("No EZ1 found. Check that Local Mode is switched on (Continuous) in the AP EasyPower app, "
                  "that the panels have sun (the EZ1 is off at night), and that this computer is on the "
                  "same network as the inverter. Your router's list of connected devices also shows its IP.",
                  file=sys.stderr)
            return 1
        if a.scan is not None:
            return 0
        if len(found) > 1:
            print("Several inverters found; pick one with --inverter IP.", file=sys.stderr)
            return 1
        a.inverter = found[0]["host"]
        print(f"Using {a.inverter}. Next time you can start with: --inverter {a.inverter}", file=sys.stderr)

    client = EZ1Client(a.inverter, a.inverter_port)
    if a.check:
        import json
        try:
            print(json.dumps(client.snapshot(), indent=2))
            return 0
        except EZ1Error as exc:
            print(f"Could not read the inverter: {exc}", file=sys.stderr)
            print("Check that Local Mode is enabled in the AP EasyPower app, that the IP is right, "
                  "and that the panels have sun (the EZ1 is off at night).", file=sys.stderr)
            return 1

    serve(client, store or Store(a.db), a.bind, a.port, a.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
