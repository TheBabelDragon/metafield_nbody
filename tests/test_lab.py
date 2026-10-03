"""Tests for the Interactive Dynamics Laboratory."""
import json
import math
import unittest

from metafield_nbody import experiment as E
from metafield_nbody import lab as Lab
from metafield_nbody import physics as P
from metafield_nbody.integrators import (
    INTEGRATORS,
    forest_ruth4_fixed,
    list_integrators,
    rk4,
    velocity_verlet,
)


class TestICValidation(unittest.TestCase):
    def test_valid_scenario_ic(self):
        ic = E.bodies_from_scenario("1")
        self.assertEqual(ic["source"], "scenario")
        self.assertFalse(ic["experimental"])
        E.validate_bodies(ic["m"], ic["x"], ic["v"])

    def test_custom_ic(self):
        ic = E.make_custom_ic(
            [1.0, 1.0],
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            [[0.0, 0.5, 0.0], [0.0, -0.5, 0.0]],
            name="binary",
        )
        self.assertTrue(ic["experimental"])
        self.assertEqual(ic["scenario_name"], "binary")

    def test_reject_zero_mass(self):
        with self.assertRaises(E.ValidationError):
            E.make_custom_ic(
                [0.0, 1.0],
                [[0, 0, 0], [1, 0, 0]],
                [[0, 0, 0], [0, 0, 0]],
            )

    def test_reject_coincident(self):
        with self.assertRaises(E.ValidationError):
            E.make_custom_ic(
                [1.0, 1.0],
                [[0, 0, 0], [0, 0, 0]],
                [[0, 0, 0], [0, 0, 0]],
            )

    def test_reject_bad_dt(self):
        with self.assertRaises(E.ValidationError):
            E.validate_run_params(-1e-3, n_steps=10, integrator_id="rk4")


class TestIntegrators(unittest.TestCase):
    def setUp(self):
        ic = E.bodies_from_scenario("1")
        self.m, self.x0, self.v0 = ic["m"], ic["x"], ic["v"]

    def test_list(self):
        lst = list_integrators()
        self.assertGreaterEqual(len(lst), 4)
        ids = {e["id"] for e in lst}
        self.assertIn("forest_ruth4_fixed", ids)
        self.assertIn("rk4", ids)

    def test_forest_ruth_matches_physics_one_step(self):
        h = 1e-3
        x1, v1 = forest_ruth4_fixed(self.m, self.x0, self.v0, h)
        x2, v2 = P.forest_ruth4_step(self.m, self.x0, self.v0, h)
        for i in range(len(self.m)):
            for c in range(3):
                self.assertEqual(x1[i][c], x2[i][c])
                self.assertEqual(v1[i][c], v2[i][c])

    def test_rk4_finite(self):
        x, v = self.x0, self.v0
        for _ in range(50):
            x, v = rk4(self.m, x, v, 1e-3)
        for i in range(len(self.m)):
            for c in range(3):
                self.assertTrue(math.isfinite(x[i][c]))
                self.assertTrue(math.isfinite(v[i][c]))

    def test_symplectic_lower_drift_than_euler(self):
        ic = E.bodies_from_scenario("1")
        cfg_fr = E.build_config(ic=ic, integrator_id="forest_ruth4_fixed",
                                dt=5e-3, n_steps=400, label="fr")
        cfg_ee = E.build_config(ic=ic, integrator_id="explicit_euler",
                                dt=5e-3, n_steps=400, label="ee")
        r_fr = Lab.run_experiment(cfg_fr, record_trajectories=False)
        r_ee = Lab.run_experiment(cfg_ee, record_trajectories=False)
        self.assertEqual(r_fr["status"], "completed")
        self.assertEqual(r_ee["status"], "completed")
        self.assertLessEqual(
            r_fr["energy_analysis"]["max_abs_drift"],
            r_ee["energy_analysis"]["max_abs_drift"] * 1.01 + 1e-15,
        )


class TestExperimentManifest(unittest.TestCase):
    def test_build_and_digest(self):
        ic = E.bodies_from_scenario("figure-8")
        cfg = E.build_config(ic=ic, integrator_id="rk4", dt=1e-3, n_steps=100)
        self.assertEqual(cfg["manifest_version"], E.MANIFEST_VERSION)
        self.assertIn("config_digest", cfg)
        self.assertEqual(len(cfg["config_digest"]), 64)

    def test_derive_preserves_parent(self):
        ic = E.bodies_from_scenario("1")
        parent = E.build_config(ic=ic, integrator_id="rk4", dt=1e-3, n_steps=50)
        child = E.derive_config(parent, {"dt": 5e-4}, label="half-dt")
        self.assertEqual(child["parent_id"], parent["experiment_id"])
        self.assertNotEqual(child["experiment_id"], parent["experiment_id"])
        self.assertAlmostEqual(child["integration"]["dt"], 5e-4)
        diffs = E.diff_configs(parent, child)
        self.assertTrue(any("dt" in d for d in diffs))

    def test_run_reproducible(self):
        ic = E.bodies_from_scenario("1")
        cfg = E.build_config(ic=ic, integrator_id="velocity_verlet",
                             dt=1e-3, n_steps=200)
        a = Lab.run_experiment(cfg, record_trajectories=False)
        b = Lab.run_experiment(cfg, record_trajectories=False)
        self.assertEqual(a["run_digest"], b["run_digest"])
        self.assertEqual(a["energy_analysis"]["rel_drift"],
                         b["energy_analysis"]["rel_drift"])


class TestLabStore(unittest.TestCase):
    def test_run_and_list(self):
        store = Lab.LabStore()
        ic = E.bodies_from_scenario("1")
        cfg = E.build_config(ic=ic, integrator_id="rk4", dt=1e-3, n_steps=50)
        r = store.run(cfg, record_trajectories=False)
        self.assertEqual(r["status"], "completed")
        lst = store.list_experiments()
        self.assertEqual(len(lst), 1)
        self.assertEqual(lst[0]["experiment_id"], cfg["experiment_id"])

    def test_derive_and_compare(self):
        store = Lab.LabStore()
        ic = E.bodies_from_scenario("1")
        cfg = E.build_config(ic=ic, integrator_id="rk4", dt=1e-3, n_steps=80)
        r1 = store.run(cfg, record_trajectories=True)
        r2 = store.derive_and_run(cfg["experiment_id"], {"integrator_id": "velocity_verlet"})
        cmp_ = Lab.compare_experiments([r1, r2])
        self.assertEqual(len(cmp_["experiments"]), 2)
        self.assertTrue(cmp_["pairwise_diffs"])

    def test_sweep(self):
        store = Lab.LabStore()
        ic = E.bodies_from_scenario("1")
        base = E.build_config(ic=ic, integrator_id="rk4", dt=1e-3, n_steps=40)
        out = store.start_sweep(
            base_config=base,
            parameter="dt",
            values=[1e-3, 2e-3, 5e-3],
        )
        self.assertTrue(out["ok"])
        import time
        for _ in range(50):
            st = store.sweep_status()
            if not st["active"]:
                break
            time.sleep(0.05)
        st = store.sweep_status()
        self.assertFalse(st["active"])
        self.assertEqual(st["completed"], 3)
        self.assertGreaterEqual(len(store.list_experiments()), 3)

    def test_trajectory_separation(self):
        store = Lab.LabStore()
        ic = E.bodies_from_scenario("1")
        cfg = E.build_config(ic=ic, integrator_id="rk4", dt=1e-3, n_steps=100)
        r1 = store.run(cfg, record_trajectories=True)
        ic2 = E.make_custom_ic(
            ic["m"],
            [[p[0] + 1e-6, p[1], p[2]] if i == 0 else list(p)
             for i, p in enumerate(ic["x"])],
            ic["v"],
            name="perturbed",
        )
        cfg2 = E.build_config(ic=ic2, integrator_id="rk4", dt=1e-3, n_steps=100)
        r2 = store.run(cfg2, record_trajectories=True)
        sep = Lab.trajectory_separation(r1, r2)
        self.assertEqual(sep["kind"], "numerical_comparison")
        self.assertGreater(sep["final_max_sep"], 0.0)


class TestExistingPhysicsUnchanged(unittest.TestCase):
    def test_operator_still_pinned(self):
        self.assertEqual(P.OPERATOR_NAME, "forest_ruth4")
        self.assertEqual(P.OPERATOR_VERSION, "1.0.0")


if __name__ == "__main__":
    unittest.main()
