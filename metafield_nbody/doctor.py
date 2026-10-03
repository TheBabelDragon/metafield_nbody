"""Diagnostic checks for scientific integrity (python -m metafield_nbody doctor)."""
from __future__ import annotations

import math
import os
import sys
import tempfile
import traceback


def _ok(name, detail=""):
    return {"name": name, "status": "OK", "detail": detail}


def _fail(name, detail):
    return {"name": name, "status": "FAIL", "detail": detail}


def check_physics():
    try:
        from . import physics as P
        from .field import NBodyField
        f = NBodyField("1")
        f.advance(10)
        inv = f.invariants()
        if not math.isfinite(inv["energy"]):
            return _fail("Physics engine", "non-finite energy after 10 ticks")
        return _ok("Physics engine", "Forest-Ruth %s; figure-8 advanced 10 ticks" % P.OPERATOR_VERSION)
    except Exception as exc:
        return _fail("Physics engine", str(exc))


def check_scenarios():
    try:
        from . import scenarios as S
        n = len(S.SCENARIOS)
        for rec in S.SCENARIOS:
            built = S.build(rec[0])
            if not built["m"]:
                return _fail("Scenarios", "empty body list for %s" % rec[0])
        return _ok("Scenarios", "%d scenarios loadable" % n)
    except Exception as exc:
        return _fail("Scenarios", str(exc))


def check_contracts():
    try:
        from .field import NBodyField
        from . import contract as C
        f = NBodyField("1")
        f.advance(5)
        errs = C.check_log(f.log)
        if errs:
            return _fail("Field contracts", "; ".join(errs[:3]))
        return _ok("Field contracts", "%d ticks admitted; chain valid" % len(f.log))
    except Exception as exc:
        return _fail("Field contracts", str(exc))


def check_replay():
    try:
        from .field import NBodyField, load_log, replay
        f = NBodyField("1")
        f.advance(20)
        path = tempfile.mktemp(suffix=".jsonl")
        try:
            f.export_log(path)
            ticks = load_log(path)
            r = replay(ticks)
            if r["digest"] != f.digest:
                return _fail("Replay", "digest mismatch after replay")
            if r["t"] != f.t or r["tick"] != f.tick_no:
                return _fail("Replay", "time/tick mismatch after replay")
            for i in range(len(f.m)):
                if r["bodies"][i]["x"] != list(f.x[i]):
                    return _fail("Replay", "body %d position mismatch" % i)
        finally:
            if os.path.exists(path):
                os.remove(path)
        return _ok("Replay", "export -> load -> replay matches live state")
    except Exception as exc:
        return _fail("Replay", str(exc))


def check_determinism():
    try:
        from .field import NBodyField
        def once():
            f = NBodyField("1")
            f.advance(40)
            return f.digest, f.t, [list(p) for p in f.x]
        a, b = once(), once()
        if a != b:
            return _fail("Determinism", "two identical runs diverged")
        return _ok("Determinism", "two 40-tick figure-8 runs bit-identical")
    except Exception as exc:
        return _fail("Determinism", str(exc))


def check_visualization():
    try:
        from .viz import VizSession
        s = VizSession("1")
        s.playing = False
        s.step(12)
        snap = s.snapshot()
        f = s.field
        if snap["sim"]["tick"] != f.tick_no:
            return _fail("Visualization", "tick mismatch in transport payload")
        if snap["bodies"][0]["x"] != list(f.x[0]):
            return _fail("Visualization", "position mismatch in transport payload")
        if snap["field"]["digest"] != f.digest:
            return _fail("Visualization", "digest mismatch in transport payload")
        static = os.path.join(os.path.dirname(__file__), "static")
        for name in ("index.html", "app.js", "style.css"):
            if not os.path.isfile(os.path.join(static, name)):
                return _fail("Visualization", "missing static/%s" % name)
        return _ok("Visualization", "payload matches NBodyField; static assets present")
    except Exception as exc:
        return _fail("Visualization", str(exc))


def check_experiments():
    try:
        from .experiment import bodies_from_scenario, build_config
        from .lab import run_experiment, LabStore
        ic = bodies_from_scenario("1")
        cfg = build_config(ic=ic, integrator_id="rk4", dt=1e-3, n_steps=30)
        r = run_experiment(cfg, record_trajectories=False)
        if r["status"] != "completed":
            return _fail("Experiment storage", "run status=%s" % r["status"])
        store = LabStore()
        store.run(cfg, record_trajectories=False)
        if len(store.list_experiments()) < 1:
            return _fail("Experiment storage", "store empty after run")
        return _ok("Experiment storage", "manifest + run_digest produced")
    except Exception as exc:
        return _fail("Experiment storage", str(exc))


def check_integrators():
    try:
        from .integrators import forest_ruth4_fixed, list_integrators
        from . import physics as P
        from .experiment import bodies_from_scenario
        ic = bodies_from_scenario("1")
        m, x, v = ic["m"], ic["x"], ic["v"]
        x1, v1 = forest_ruth4_fixed(m, x, v, 1e-3)
        x2, v2 = P.forest_ruth4_step(m, x, v, 1e-3)
        if x1 != x2 or v1 != v2:
            return _fail("Integrators", "lab FR fixed != physics FR operator")
        n = len(list_integrators())
        return _ok("Integrators", "%d lab methods; FR fixed matches Field operator" % n)
    except Exception as exc:
        return _fail("Integrators", str(exc))


CHECKS = [
    check_physics,
    check_scenarios,
    check_contracts,
    check_replay,
    check_determinism,
    check_visualization,
    check_experiments,
    check_integrators,
]


def run_all():
    results = []
    for fn in CHECKS:
        try:
            results.append(fn())
        except Exception as exc:
            results.append(_fail(fn.__name__, traceback.format_exc(limit=2)))
    return results


def main(argv=None):
    print("MetaField N-Body · doctor")
    print("-" * 48)
    results = run_all()
    width = max(len(r["name"]) for r in results)
    failed = 0
    for r in results:
        mark = r["status"]
        if mark != "OK":
            failed += 1
        line = "%-*s  %s" % (width, r["name"], mark)
        if r.get("detail"):
            line += "  — " + r["detail"]
        print(line)
    print("-" * 48)
    if failed:
        print("%d check(s) failed" % failed)
        return 1
    print("All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
