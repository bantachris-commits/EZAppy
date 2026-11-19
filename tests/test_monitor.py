import json
import threading
import time
import unittest
import urllib.request

from ez1monitor.ez1 import EZ1Client, EZ1Error
from ez1monitor.server import Poller, make_handler
from ez1monitor.simulator import SimState, backfill, make_server
from ez1monitor.store import Store
from http.server import ThreadingHTTPServer


class MonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sim = make_server("127.0.0.1", 0)
        threading.Thread(target=cls.sim.serve_forever, daemon=True).start()
        cls.client = EZ1Client("127.0.0.1", cls.sim.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.sim.shutdown()

    def test_snapshot_shape(self):
        s = self.client.snapshot()
        self.assertTrue(s["online"])
        self.assertEqual(s["device"]["device_id"], "E07000000001")
        self.assertAlmostEqual(s["output"]["power"], s["output"]["p1"] + s["output"]["p2"])
        self.assertEqual(s["max_power"], 800)
        self.assertTrue(s["on"])
        self.assertEqual(set(s["alarms"]), {"off_grid", "dc1_short_circuit", "dc2_short_circuit", "output_fault"})
        self.assertFalse(any(s["alarms"].values()))

    def test_unreachable_raises(self):
        with self.assertRaises(EZ1Error):
            EZ1Client("127.0.0.1", 1, timeout=1).output_data()

    def test_daily_survives_midday_restart(self):
        st = Store(":memory:")
        base = int(time.time()) - 3600
        st.add_sample(base, 100, 100, 1.0, 50.0)
        st.add_sample(base + 60, 100, 100, 0.1, 51.5)  # inverter restarted, e_today reset
        today = st.daily(1)[-1]
        self.assertAlmostEqual(today["energy"], 1.5)
        self.assertEqual(today["peak_w"], 200)

    def test_poller_offline_then_api(self):
        st = Store(":memory:")
        backfill(st, SimState(), days=2)
        bad = Poller(EZ1Client("127.0.0.1", 1, timeout=1), st)
        self.assertFalse(bad.poll_once())
        self.assertFalse(bad.state["online"])

        poller = Poller(self.client, st)
        self.assertTrue(poller.poll_once())
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(poller, st))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            get = lambda p: urllib.request.urlopen(base + p, timeout=5).read()  # noqa: E731
            status = json.loads(get("/api/status"))
            self.assertTrue(status["online"])
            self.assertGreater(len(json.loads(get("/api/history?hours=48"))), 10)
            self.assertGreaterEqual(len(json.loads(get("/api/daily?days=7"))), 2)
            self.assertIn(b"EZ1 Monitor", get("/"))
        finally:
            httpd.shutdown()


if __name__ == "__main__":
    unittest.main()
