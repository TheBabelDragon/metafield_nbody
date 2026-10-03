"""Scientific integrity: independent invariants, authority chain, replay, corruption.

These tests do NOT call production invariant helpers to "verify" themselves.
Independent formulae are coded inline and compared to production outputs.
"""
from __future__ import annotations

import math
import os
import tempfile
import unittest
from math import sqrt

from metafield_nbody import contract as C
from metafield_nbody import physics as P
from metafield_nbody.experiment import bodies_from_scenario, build_config, ValidationError
from metafield_nbody.field import NBodyField, load_log, replay
from metafield_nbody.integrators import forest_ruth4_fixed, get_step, list_integrators
from metafield_nbody.lab import run_experiment
from metafield_nbody.viz import VizSession


def independent_invariants(m, x, v, G=1.0, soft2=1e-12):
    """Independent K, U (softened), E, P, L — same model assumptions as production."""
    n = len(m)
    ke = 0.0
    px = py = pz = 0.0
    lx = ly = lz = 0.0
    mt = 0.0
    cx = cy = cz = 0.0
    for i in range(n):
        mi = m[i]
        xi, yi, zi = x[i]
        vxi, vyi, vzi = v[i]
        ke += 0.5 * mi * (vxi * vxi + vyi * vyi + vzi * vzi)
        px += mi * vxi
        py += mi * vyi
        pz += mi * vzi
        lx += mi * (yi * vzi - zi * vyi)
        ly += mi * (zi * vxi - xi * vzi)
        lz += mi * (xi * vyi - yi * vxi)
        mt += mi
        cx += mi * xi
        cy += mi * yi
        cz += mi * zi
    pe = 0.0
    for i in range(n - 1):
        for j in range(i + 1, n):
            dx = x[j][0] - x[i][0]
            dy = x[j][1] - x[i][1]
            dz = x[j][2] - x[i][2]
            pe -= G * m[i] * m[j] / sqrt(dx * dx + dy * dy + dz * dz + soft2)
    return {
        "kinetic": ke,
        "potential": pe,
        "energy": ke + pe,
        "momentum": [px, py, pz],
        "angular_momentum": [lx, ly, lz],
        "mass": mt,
        "com": [cx / mt, cy / mt, cz / mt] if mt else [0.0, 0.0, 0.0],
    }


class TestIndependentInvariants(unittest.TestCase):
    def _check_scenario(self, sel, steps=50):
        f = NBodyField(sel)
        f.advance(steps)
        prod = P.invariants(f.m, f.x, f.v)
        ind = independent_invariants(f.m, f.x, f.v, G=P.G, soft2=P.EPS2)
        self.assertEqual(prod["kinetic"], ind["kinetic"])
        self.assertEqual(prod["potential"], ind["potential"])
        self.assertEqual(prod["energy"], ind["energy"])
        self.assertEqual(prod["momentum"], ind["momentum"])
        self.assertEqual(prod["angular_momentum"], ind["angular_momentum"])
        self.assertEqual(prod["mass"], ind["mass"])
        self.assertEqual(prod["com"], ind["com"])

    def test_figure8(self):
        self._check_scenario("1", 100)

    def test_burrau(self):
        self._check_scenario("burrau", 40)

    def test_lagrange(self):
        self._check_scenario("lagrange-chaos", 40)

    def test_units_documented(self):
        self.assertEqual(P.G, 1.0)
        self.assertEqual(P.SOFTENING, 1e-6)
        self.assertEqual(P.EPS2, P.SOFTENING * P.SOFTENING)


class TestAuthorityChain(unittest.TestCase):
    def test_field_to_viz_snapshot(self):
        f = NBodyField("1")
        f.advance(25)
        s = VizSession("1")
        s.playing = False
        s.step(25)
        snap = s.snapshot()
        self.assertEqual(snap["sim"]["body_count"], len(f.m))
        self.assertEqual(snap["sim"]["tick"], f.tick_no)
        self.assertEqual(snap["sim"]["t"], f.t)
        self.assertEqual(snap["invariants"]["energy"], f.invariants()["energy"])
        for i in range(len(f.m)):
            self.assertEqual(snap["bodies"][i]["id"], i)
            self.assertEqual(snap["bodies"][i]["m"], f.m[i])
            self.assertEqual(snap["bodies"][i]["x"], list(f.x[i]))
            self.assertEqual(snap["bodies"][i]["v"], list(f.v[i]))
        self.assertEqual(snap["field"]["digest"], f.digest)
        self.assertEqual(snap["field"]["operator"]["name"], P.OPERATOR_NAME)

    def test_no_interpolation_in_payload(self):
        s = VizSession("1")
        s.playing = False
        s.step(10)
        snap = s.snapshot()
        f = s.field
        for i in range(len(f.m)):
            self.assertEqual(snap["bodies"][i]["x"], list(f.x[i]))


class TestIntegrators(unittest.TestCase):
    def test_fr_fixed_matches_physics_operator(self):
        ic = bodies_from_scenario("1")
        m, x, v = ic["m"], ic["x"], ic["v"]
        h = 1e-3
        x1, v1 = forest_ruth4_fixed(m, x, v, h)
        x2, v2 = P.forest_ruth4_step(m, x, v, h)
        for i in range(len(m)):
            self.assertEqual(x1[i], x2[i])
            self.assertEqual(v1[i], v2[i])

    def test_all_integrators_one_step_finite(self):
        ic = bodies_from_scenario("1")
        m, x0, v0 = ic["m"], ic["x"], ic["v"]
        for info in list_integrators():
            step = get_step(info["id"])
            x, v = step(m, x0, v0, 1e-3)
            for i in range(len(m)):
                for c in range(3):
                    self.assertTrue(math.isfinite(x[i][c]), info["id"])
                    self.assertTrue(math.isfinite(v[i][c]), info["id"])

    def test_invalid_dt_rejected(self):
        ic = bodies_from_scenario("1")
        with self.assertRaises(ValidationError):
            build_config(ic=ic, integrator_id="rk4", dt=-1e-3, n_steps=10)

    def test_deterministic_lab_repeat(self):
        ic = bodies_from_scenario("1")
        cfg = build_config(ic=ic, integrator_id="velocity_verlet", dt=1e-3, n_steps=200)
        a = run_experiment(cfg, record_trajectories=False)
        b = run_experiment(cfg, record_trajectories=False)
        self.assertEqual(a["run_digest"], b["run_digest"])
        self.assertEqual(a["final_state"]["x"], b["final_state"]["x"])


class TestFieldDeterminism(unittest.TestCase):
    def test_two_runs_identical(self):
        def run():
            f = NBodyField("1")
            f.advance(80)
            return {
                "t": f.t,
                "tick": f.tick_no,
                "digest": f.digest,
                "x": [list(p) for p in f.x],
                "v": [list(q) for q in f.v],
                "energy": f.invariants()["energy"],
            }
        self.assertEqual(run(), run())


class TestReplay(unittest.TestCase):
    def test_export_replay_matches_live(self):
        f = NBodyField("figure-8")
        f.advance(30)
        path = tempfile.mktemp(suffix=".jsonl")
        try:
            f.export_log(path)
            ticks = load_log(path)
            r = replay(ticks)
            self.assertEqual(r["t"], f.t)
            self.assertEqual(r["tick"], f.tick_no)
            self.assertEqual(r["digest"], f.digest)
            for i in range(len(f.m)):
                self.assertEqual(r["bodies"][i]["m"], f.m[i])
                self.assertEqual(r["bodies"][i]["x"], list(f.x[i]))
                self.assertEqual(r["bodies"][i]["v"], list(f.v[i]))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_corrupt_digest_rejected(self):
        f = NBodyField("1")
        f.advance(15)
        path = tempfile.mktemp(suffix=".jsonl")
        try:
            f.export_log(path)
            ticks = load_log(path)
            ticks[len(ticks) // 2]["digest"] = "0" * 64
            with self.assertRaises(C.ContractViolation):
                replay(ticks)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_corrupt_numeric_rejected(self):
        f = NBodyField("1")
        f.advance(15)
        path = tempfile.mktemp(suffix=".jsonl")
        try:
            f.export_log(path)
            ticks = load_log(path)
            d0 = ticks[-1]["deltas"][0]
            if isinstance(d0["value"], dict) and "x" in d0["value"]:
                d0["value"]["x"][0] += 1.0
            else:
                ticks[-1]["t"] += 1.0
            with self.assertRaises(C.ContractViolation):
                replay(ticks)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_corrupt_tick_number_rejected(self):
        f = NBodyField("1")
        f.advance(10)
        path = tempfile.mktemp(suffix=".jsonl")
        try:
            f.export_log(path)
            ticks = load_log(path)
            ticks[3]["tick"] = 999
            with self.assertRaises(C.ContractViolation):
                replay(ticks)
        finally:
            if os.path.exists(path):
                os.remove(path)


class TestExperimentProvenance(unittest.TestCase):
    def test_manifest_fields(self):
        ic = bodies_from_scenario("1")
        cfg = build_config(ic=ic, integrator_id="rk4", dt=1e-3, n_steps=50, label="prov-test")
        for k in ("manifest_version", "experiment_id", "config_digest", "ic", "model", "integration", "software"):
            self.assertIn(k, cfg)
        result = run_experiment(cfg, record_trajectories=False)
        self.assertIn("run_digest", result)
        self.assertEqual(result["config"]["experiment_id"], cfg["experiment_id"])


class TestNormalization(unittest.TestCase):
    def test_g_is_one(self):
        self.assertEqual(P.G, 1.0)

    def test_softening_in_force_and_energy(self):
        m = [1.0, 1.0]
        x = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
        v = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
        inv = P.invariants(m, x, v)
        expected_pe = -P.G * 1.0 * 1.0 / sqrt(1.0 + P.EPS2)
        self.assertEqual(inv["potential"], expected_pe)


if __name__ == "__main__":
    unittest.main()
