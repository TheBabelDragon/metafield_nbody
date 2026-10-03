"""Local Celestial Field Observatory \u2014 scientific 3D visualization for NBodyField.\n\nArchitecture:\n  NBodyField (authoritative) \u2500\u2500\u25ba VizSession (state + history)\n                                      \u2502\n                                      \u25bc\n                              HTTP + SSE server (stdlib only)\n                                      \u2502\n                                      \u25bc\n                              Browser (Three.js + telemetry UI)\n\nLaunch:  python -m metafield_nbody viz [--scenario figure-8] [--port 8765]\n"""
from __future__ import annotations

import argparse
import json
import math
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import contract as C
from . import physics as P
from . import scenarios as S
from .field import NBodyField

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
DEFAULT_PORT = 8765
HISTORY_CAP = 4000
TRAIL_CAP = 1500
PERM_TRAIL_CAP = 8000
PERM_TRAIL_STRIDE = 2


class VizSession:
    """Thread-safe wrapper around one live NBodyField plus history buffers."""

    def __init__(self, scenario: str = "1"):
        self._lock = threading.RLock()
        self.field = NBodyField(scenario)
        self.playing = True
        self.speed = 1.0
        self._last_step = time.monotonic()
        self.history: list[dict] = []
        self.permanent_trails: list[list] = [[] for _ in self.field.m]
        self._perm_stride_counter = 0
        self._record_snapshot()

    def _clear_permanent_trails(self):
        n = len(self.field.m)
        self.permanent_trails = [[] for _ in range(n)]
        self._perm_stride_counter = 0

    def _append_permanent(self, force: bool = False):
        f = self.field
        n = len(f.m)
        if len(self.permanent_trails) != n:
            self.permanent_trails = [[] for _ in range(n)]
        self._perm_stride_counter += 1
        if not force and (self._perm_stride_counter % PERM_TRAIL_STRIDE) != 0:
            return
        for i in range(n):
            self.permanent_trails[i].append({
                "x": list(f.x[i]),
                "v": list(f.v[i]),
                "t": f.t,
                "tick": f.tick_no,
            })
            if len(self.permanent_trails[i]) > PERM_TRAIL_CAP:
                self.permanent_trails[i] = self.permanent_trails[i][-PERM_TRAIL_CAP:]

    def _record_snapshot(self):
        f = self.field
        inv = f.invariants()
        snap = {
            "tick": f.tick_no,
            "t": f.t,
            "digest": f.digest,
            "bodies": [
                {"m": f.m[i], "x": list(f.x[i]), "v": list(f.v[i])}
                for i in range(len(f.m))
            ],
            "energy": inv["energy"],
            "kinetic": inv["kinetic"],
            "potential": inv["potential"],
            "energy_drift": inv["energy_drift"],
            "momentum": inv["momentum"],
            "angular_momentum": inv["angular_momentum"],
            "com": inv["com"],
        }
        self.history.append(snap)
        if len(self.history) > HISTORY_CAP:
            self.history = self.history[-HISTORY_CAP:]
        self._append_permanent(force=(f.tick_no == 0))

    def snapshot(self) -> dict:
        with self._lock:
            f = self.field
            inv = f.invariants()
            last_tick = f.log[-1] if f.log else None
            trails = [[] for _ in f.m]
            for snap in self.history[-TRAIL_CAP:]:
                for i, b in enumerate(snap["bodies"]):
                    if i < len(trails):
                        trails[i].append(b["x"])
            a = P.accelerations(f.m, f.x)
            pairs = []
            n = len(f.m)
            for i in range(n - 1):
                for j in range(i + 1, n):
                    dx = f.x[j][0] - f.x[i][0]
                    dy = f.x[j][1] - f.x[i][1]
                    dz = f.x[j][2] - f.x[i][2]
                    r2 = dx * dx + dy * dy + dz * dz + P.EPS2
                    r = math.sqrt(r2)
                    pairs.append({
                        "i": i, "j": j,
                        "r": r,
                        "force_mag": P.G * f.m[i] * f.m[j] / (r2 * math.sqrt(r2)),
                    })
            return {
                "ok": True,
                "scenario": {"key": f.key, "name": f.name, "note": f.note,
                             "period": f.period, "eta": f.eta},
                "sim": {
                    "t": f.t, "tick": f.tick_no,
                    "paused": f.paused or not self.playing,
                    "playing": self.playing and not f.paused,
                    "speed": self.speed,
                    "steps_per_tick": f.steps_per_tick,
                    "body_count": len(f.m),
                },
                "bodies": [
                    {"id": i, "m": f.m[i], "x": list(f.x[i]),
                     "v": list(f.v[i]), "a": list(a[i])}
                    for i in range(len(f.m))
                ],
                "trails": trails,
                "permanent_trails": [
                    [{"x": s["x"], "v": s["v"], "t": s["t"], "tick": s["tick"]}
                     for s in body_trail]
                    for body_trail in self.permanent_trails
                ],
                "permanent_trail_meta": {
                    "cap": PERM_TRAIL_CAP,
                    "stride": PERM_TRAIL_STRIDE,
                    "points": sum(len(t) for t in self.permanent_trails),
                },
                "invariants": {
                    "energy": inv["energy"], "kinetic": inv["kinetic"],
                    "potential": inv["potential"],
                    "energy_drift": inv["energy_drift"],
                    "energy0": f.inv0["energy"],
                    "momentum": inv["momentum"],
                    "angular_momentum": inv["angular_momentum"],
                    "mass": inv["mass"], "com": inv["com"],
                },
                "field": {
                    "digest": f.digest,
                    "prev_digest": last_tick["prev_digest"] if last_tick else None,
                    "tick_count": len(f.log),
                    "last_dt": last_tick["dt"] if last_tick else 0.0,
                    "contract_ok": True,
                    "operator": {"name": P.OPERATOR_NAME, "version": P.OPERATOR_VERSION},
                    "params": {
                        "G": P.G, "softening": P.SOFTENING, "eta": f.eta,
                        "dt_min": P.DT_MIN, "dt_max": P.DT_MAX, "theta": P.THETA,
                    },
                },
                "pairs": pairs,
                "history": {
                    "t": [h["t"] for h in self.history],
                    "energy": [h["energy"] for h in self.history],
                    "energy_drift": [h["energy_drift"] for h in self.history],
                    "momentum_mag": [
                        math.sqrt(sum(c * c for c in h["momentum"]))
                        for h in self.history
                    ],
                    "L_mag": [
                        math.sqrt(sum(c * c for c in h["angular_momentum"]))
                        for h in self.history
                    ],
                },
                "math": {
                    "integrator": "Forest-Ruth 4th-order symplectic (three leapfrogs)",
                    "force": "Newtonian gravity with Plummer softening",
                    "equations": {
                        "dr_dt": "dr_i / dt = v_i",
                        "dv_dt": "dv_i / dt = G \u03a3_{j\u2260i} m_j (r_j - r_i) / (|r_j - r_i|\u00b2 + \u03b5\u00b2)^{3/2}",
                        "energy": "E = \u03a3 \u00bd m_i |v_i|\u00b2 \u2212 \u03a3_{i<j} G m_i m_j / \u221a(|r_i-r_j|\u00b2 + \u03b5\u00b2)",
                        "momentum": "P = \u03a3 m_i v_i",
                        "angular_momentum": "L = \u03a3 m_i (r_i \u00d7 v_i)",
                    },
                    "notes": [
                        "G = 1 (normalized units)",
                        f"Softening \u03b5 = {P.SOFTENING} (Plummer)",
                        "Adaptive dt = \u03b7 \u00b7 min(free-fall, fly-by) over pairs",
                        "Adaptive dt is not strictly symplectic",
                        "Primary operator uses only + \u2212 * / \u221a (IEEE-754 bit-identical)",
                    ],
                },
            }

    def step(self, n: int = 1):
        with self._lock:
            ticks = self.field.advance(n)
            for _ in ticks:
                self._record_snapshot()
            return len(ticks)

    def tick_loop(self):
        while True:
            time.sleep(0.016)
            with self._lock:
                if not self.playing or self.field.paused or self.field.quit:
                    self._last_step = time.monotonic()
                    continue
                now = time.monotonic()
                elapsed = now - self._last_step
                target = self.speed * elapsed
                n = int(target)
                if n >= 1:
                    ticks = self.field.advance(n)
                    for _ in ticks:
                        self._record_snapshot()
                    self._last_step = now

    def command(self, cmd: str, arg=None) -> dict:
        with self._lock:
            if cmd == "play":
                self.playing = True
                self.field.paused = False
                self._last_step = time.monotonic()
                return {"ok": True, "msg": "playing"}
            if cmd == "pause":
                self.playing = False
                return {"ok": True, "msg": "paused"}
            if cmd == "toggle":
                self.playing = not self.playing
                if self.playing:
                    self.field.paused = False
                    self._last_step = time.monotonic()
                return {"ok": True, "msg": "playing" if self.playing else "paused"}
            if cmd == "step":
                n = int(arg) if arg is not None else 1
                self.playing = False
                got = self.step(n)
                return {"ok": True, "msg": f"{got} ticks"}
            if cmd == "reset":
                self.field.command("reset")
                self.history = []
                self._clear_permanent_trails()
                self._record_snapshot()
                self.playing = False
                return {"ok": True, "msg": "reset"}
            if cmd == "select":
                ok, msg = self.field.select(arg)
                if ok:
                    self.history = []
                    self._clear_permanent_trails()
                    self._record_snapshot()
                    self.playing = False
                return {"ok": ok, "msg": msg}
            if cmd == "clear_permanent_trails":
                self._clear_permanent_trails()
                self._append_permanent(force=True)
                return {"ok": True, "msg": "permanent trails cleared"}
            if cmd == "speed":
                try:
                    sp = float(arg)
                    self.speed = max(0.1, min(200.0, sp))
                    return {"ok": True, "msg": f"speed={self.speed}"}
                except (TypeError, ValueError):
                    return {"ok": False, "msg": "invalid speed"}
            if cmd == "export_log":
                path = arg or "/tmp/nbody_viz_export.jsonl"
                self.field.export_log(path)
                return {"ok": True, "msg": path, "ticks": len(self.field.log)}
            return {"ok": False, "msg": f"unknown command {cmd!r}"}


class VizHandler(BaseHTTPRequestHandler):
    session: VizSession = None

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            return
        super().log_message(fmt, *args)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code, obj):
        body = json.dumps(obj, allow_nan=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype="text/html"):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self._file(os.path.join(STATIC_DIR, "index.html"))
            return
        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            full = os.path.join(STATIC_DIR, rel)
            if not os.path.abspath(full).startswith(os.path.abspath(STATIC_DIR)):
                self.send_error(403)
                return
            ext = os.path.splitext(full)[1].lower()
            mime = {".js": "application/javascript", ".css": "text/css",
                    ".html": "text/html", ".json": "application/json",
                    ".svg": "image/svg+xml"}.get(ext, "application/octet-stream")
            self._file(full, mime)
            return
        if path == "/api/state":
            self._json(200, self.session.snapshot())
            return
        if path == "/api/scenarios":
            out = [{"key": r[0], "name": r[1], "note": r[7], "period": r[5]}
                   for r in S.SCENARIOS]
            self._json(200, {"scenarios": out})
            return
        if path == "/api/tick":
            qs = parse_qs(parsed.query)
            idx = int(qs.get("i", ["-1"])[0])
            with self.session._lock:
                log = self.session.field.log
                if 0 <= idx < len(log):
                    self._json(200, {"ok": True, "tick": log[idx]})
                else:
                    self._json(200, {"ok": False, "msg": "out of range",
                                     "count": len(log)})
            return
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/command":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "msg": "bad json"})
            return
        result = self.session.command(data.get("cmd", ""), data.get("arg"))
        self._json(200, result)


def run_server(scenario: str = "1", port: int = DEFAULT_PORT, open_browser: bool = True):
    session = VizSession(scenario)
    VizHandler.session = session
    t = threading.Thread(target=session.tick_loop, daemon=True)
    t.start()
    server = ThreadingHTTPServer(("127.0.0.1", port), VizHandler)
    url = f"http://127.0.0.1:{port}/"
    print(f"MetaField N-Body \u00b7 Celestial Field Observatory")
    print(f"  scenario : {session.field.name}")
    print(f"  URL      : {url}")
    print(f"  Ctrl-C to stop")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        server.server_close()


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="metafield_nbody viz",
        description="Launch the Celestial Field Observatory (local 3D scientific visualizer).",
    )
    ap.add_argument("--scenario", "-s", default="1",
                    help="scenario key or name (default: figure-8)")
    ap.add_argument("--port", "-p", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-browser", action="store_true",
                    help="do not open a browser window")
    args = ap.parse_args(argv)
    run_server(args.scenario, args.port, open_browser=not args.no_browser)
    return 0
