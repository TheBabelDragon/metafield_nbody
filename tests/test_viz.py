"""Tests for the Celestial Field Observatory visualization layer."""
import json
import os
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection

from metafield_nbody.field import NBodyField
from metafield_nbody.viz import VizSession, VizHandler, DEFAULT_PORT
from metafield_nbody import scenarios as S


class TestVizSession(unittest.TestCase):
    def test_genesis_snapshot(self):
        s = VizSession("1")
        snap = s.snapshot()
        self.assertTrue(snap["ok"])
        self.assertEqual(snap["scenario"]["name"], "figure-8")
        self.assertEqual(snap["sim"]["tick"], 0)
        self.assertEqual(snap["sim"]["body_count"], 3)
        self.assertEqual(len(snap["bodies"]), 3)
        self.assertIn("energy", snap["invariants"])
        self.assertIn("digest", snap["field"])
        self.assertEqual(len(s.history), 1)

    def test_step_advances_and_records(self):
        s = VizSession("1")
        s.playing = False
        n = s.step(5)
        self.assertEqual(n, 5)
        self.assertEqual(s.field.tick_no, 5)
        self.assertEqual(len(s.history), 6)
        snap = s.snapshot()
        self.assertEqual(snap["sim"]["tick"], 5)
        self.assertGreater(snap["sim"]["t"], 0.0)

    def test_reset_clears_history(self):
        s = VizSession("1")
        s.step(4)
        r = s.command("reset")
        self.assertTrue(r["ok"])
        self.assertEqual(s.field.tick_no, 0)
        self.assertEqual(len(s.history), 1)
        self.assertEqual(s.history[0]["tick"], 0)

    def test_select_scenario(self):
        s = VizSession("1")
        r = s.command("select", "burrau")
        self.assertTrue(r["ok"])
        self.assertEqual(s.field.name, "burrau")
        self.assertEqual(s.field.tick_no, 0)
        snap = s.snapshot()
        self.assertEqual(snap["scenario"]["name"], "burrau")
        masses = sorted(b["m"] for b in snap["bodies"])
        self.assertEqual(masses, [3.0, 4.0, 5.0])

    def test_invalid_scenario(self):
        s = VizSession("1")
        r = s.command("select", "no-such-scenario")
        self.assertFalse(r["ok"])
        self.assertEqual(s.field.name, "figure-8")

    def test_pause_play(self):
        s = VizSession("1")
        s.command("pause")
        self.assertFalse(s.playing)
        s.command("play")
        self.assertTrue(s.playing)
        s.command("toggle")
        self.assertFalse(s.playing)

    def test_speed_clamp(self):
        s = VizSession("1")
        s.command("speed", 0.01)
        self.assertGreaterEqual(s.speed, 0.1)
        s.command("speed", 9999)
        self.assertLessEqual(s.speed, 200.0)
        s.command("speed", 12.5)
        self.assertEqual(s.speed, 12.5)

    def test_export_log(self):
        s = VizSession("1")
        s.step(3)
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "out.jsonl")
            r = s.command("export_log", path)
            self.assertTrue(r["ok"])
            self.assertEqual(r["ticks"], 4)
            with open(path) as f:
                lines = [ln for ln in f if ln.strip()]
            self.assertEqual(len(lines), 4)
            tk = json.loads(lines[0])
            self.assertEqual(tk["kind"], "FieldTick")
            self.assertEqual(tk["tick"], 0)

    def test_snapshot_matches_field(self):
        s = VizSession("figure-8")
        s.step(10)
        snap = s.snapshot()
        f = s.field
        self.assertEqual(snap["sim"]["t"], f.t)
        self.assertEqual(snap["sim"]["tick"], f.tick_no)
        self.assertEqual(snap["field"]["digest"], f.digest)
        for i, b in enumerate(snap["bodies"]):
            self.assertEqual(b["m"], f.m[i])
            self.assertEqual(b["x"], list(f.x[i]))
            self.assertEqual(b["v"], list(f.v[i]))
        inv = f.invariants()
        self.assertEqual(snap["invariants"]["energy"], inv["energy"])
        self.assertEqual(snap["invariants"]["energy_drift"], inv["energy_drift"])

    def test_all_scenarios_init(self):
        for rec in S.SCENARIOS:
            s = VizSession(rec[0])
            snap = s.snapshot()
            self.assertEqual(snap["scenario"]["name"], rec[1])
            self.assertEqual(snap["sim"]["body_count"], len(s.field.m))
            self.assertGreater(len(snap["bodies"]), 0)

    def test_determinism_preserved(self):
        a = VizSession("1")
        a.step(30)
        b = VizSession("1")
        b.step(30)
        self.assertEqual(a.field.digest, b.field.digest)
        self.assertEqual(
            [h["digest"] for h in a.history],
            [h["digest"] for h in b.history],
        )

    def test_math_payload_present(self):
        s = VizSession("1")
        snap = s.snapshot()
        self.assertIn("integrator", snap["math"])
        self.assertIn("equations", snap["math"])
        self.assertIn("dr_dt", snap["math"]["equations"])
        self.assertIn("Forest-Ruth", snap["math"]["integrator"])


class TestVizHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        cls.session = VizSession("1")
        VizHandler.session = cls.session
        cls.port = 18765
        cls.server = ThreadingHTTPServer(("127.0.0.1", cls.port), VizHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.15)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _get(self, path):
        c = HTTPConnection("127.0.0.1", self.port, timeout=3)
        c.request("GET", path)
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, body

    def _post(self, path, obj):
        c = HTTPConnection("127.0.0.1", self.port, timeout=3)
        payload = json.dumps(obj).encode()
        c.request("POST", path, body=payload,
                  headers={"Content-Type": "application/json"})
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, body

    def test_index(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Celestial Field Observatory", body)

    def test_static_js(self):
        status, body = self._get("/static/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"THREE", body)

    def test_api_state_structure(self):
        status, body = self._get("/api/state")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        for key in ("scenario", "sim", "bodies", "invariants", "field", "math", "history"):
            self.assertIn(key, data)
        self.assertEqual(data["scenario"]["name"], "figure-8")

    def test_api_scenarios(self):
        status, body = self._get("/api/scenarios")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(len(data["scenarios"]), 10)

    def test_api_command_step(self):
        before = self.session.field.tick_no
        status, body = self._post("/api/command", {"cmd": "step", "arg": 2})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertEqual(self.session.field.tick_no, before + 2)

    def test_api_command_select(self):
        status, body = self._post("/api/command", {"cmd": "select", "arg": "2"})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertEqual(self.session.field.name, "butterfly-i")
        self._post("/api/command", {"cmd": "select", "arg": "1"})

    def test_api_invalid_command(self):
        status, body = self._post("/api/command", {"cmd": "frobnicate"})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertFalse(data["ok"])

    def test_api_tick_out_of_range(self):
        status, body = self._get("/api/tick?i=99999")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertFalse(data["ok"])


if __name__ == "__main__":
    unittest.main()
