"""Tests for the logarithmic Hamiltonian (extended phase-space) integrator."""
import os
import sys
import unittest
from math import sqrt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metafield_nbody import physics as P
from metafield_nbody import logh as LH
from metafield_nbody.integrators import get_step, list_integrators


def _circular_binary(dim=3, a=1.0):
    m = [1.0, 1.0]
    omega = sqrt(2.0 / (a * a * a))
    x = [[0.0] * dim for _ in range(2)]
    v = [[0.0] * dim for _ in range(2)]
    x[0][0] = -0.5 * a
    x[1][0] = 0.5 * a
    v[0][1] = -0.5 * omega * a
    v[1][1] = 0.5 * omega * a
    return m, x, v


def _three_body_randomish(dim=3):
    m = [1.0, 1.2, 0.8]
    x = [[0.0] * dim for _ in range(3)]
    v = [[0.0] * dim for _ in range(3)]
    x[0][0], x[1][0], x[2][0] = -1.0, 0.5, 0.6
    x[1][1], x[2][1] = 0.7, -0.5
    if dim >= 3:
        x[2][2] = 0.2
    if dim >= 4:
        x[1][3] = 0.15
    v[0][1], v[1][0], v[2][1] = 0.1, -0.05, 0.08
    return m, x, v


class Registry(unittest.TestCase):
    def test_registered(self):
        ids = [e["id"] for e in list_integrators()]
        self.assertIn("logh_leapfrog", ids)
        self.assertIn("logh_yoshida4", ids)
        self.assertTrue(callable(get_step("logh_leapfrog")))
        self.assertTrue(callable(get_step("logh_yoshida4")))


class TwoBody(unittest.TestCase):
    def test_bound_orbit_stays_bound(self):
        m, x, v = _circular_binary(dim=3)
        inv0 = P.invariants(m, x, v, dim=3)
        self.assertLess(inv0["energy"], 0.0)
        dtau = 0.01
        xx, vv = [list(p) for p in x], [list(q) for q in v]
        t = 0.0
        B = -inv0["energy"]
        for _ in range(500):
            xx, vv, t, info = LH.logh_leapfrog_step(
                m, xx, vv, dtau, dim=3, B=B, t=t
            )
            self.assertTrue(info["converged"])
        inv1 = P.invariants(m, xx, vv, dim=3)
        self.assertLess(inv1["energy"], 0.0)
        rel = abs(inv1["energy"] - inv0["energy"]) / abs(inv0["energy"])
        self.assertLess(rel, 0.05)

    def test_physical_time_advances(self):
        m, x, v = _circular_binary(dim=3)
        inv0 = P.invariants(m, x, v, dim=3)
        B = -inv0["energy"]
        _, _, t, _ = LH.logh_leapfrog_step(m, x, v, 0.05, dim=3, B=B, t=0.0)
        self.assertGreater(t, 0.0)

    def test_momentum_conserved(self):
        m, x, v = _circular_binary(dim=3)
        inv0 = P.invariants(m, x, v, dim=3)
        B = -inv0["energy"]
        xx, vv = [list(p) for p in x], [list(q) for q in v]
        t = 0.0
        for _ in range(200):
            xx, vv, t, _ = LH.logh_leapfrog_step(
                m, xx, vv, 0.02, dim=3, B=B, t=t
            )
        inv1 = P.invariants(m, xx, vv, dim=3)
        for c in range(3):
            self.assertAlmostEqual(
                inv0["momentum"][c], inv1["momentum"][c], places=10
            )

    def test_dim4_runs(self):
        m, x, v = _circular_binary(dim=4)
        inv0 = P.invariants(m, x, v, dim=4)
        B = -inv0["energy"] if inv0["energy"] < 0 else 1.0
        xx, vv, t, info = LH.logh_leapfrog_step(
            m, x, v, 0.02, dim=4, B=B, t=0.0
        )
        self.assertEqual(len(xx[0]), 4)
        self.assertTrue(info["converged"])
        self.assertGreater(t, 0.0)


class Yoshida4(unittest.TestCase):
    def test_bound_and_order_flag(self):
        m, x, v = _circular_binary(dim=3)
        inv0 = P.invariants(m, x, v, dim=3)
        B = -inv0["energy"]
        xx, vv, t, info = LH.logh_yoshida4_step(
            m, x, v, 0.05, dim=3, B=B, t=0.0
        )
        self.assertEqual(info["order"], 4)
        self.assertTrue(info["converged"])
        self.assertGreater(t, 0.0)

    def test_lower_energy_error_than_leapfrog(self):
        """At the same Δτ and step count, 4th-order should drift less."""
        m, x, v = _circular_binary(dim=3)
        inv0 = P.invariants(m, x, v, dim=3)
        B = -inv0["energy"]
        dtau = 0.05
        n = 100

        x2, v2 = [list(p) for p in x], [list(q) for q in v]
        t = 0.0
        for _ in range(n):
            x2, v2, t, _ = LH.logh_leapfrog_step(
                m, x2, v2, dtau, dim=3, B=B, t=t
            )
        err2 = abs(P.invariants(m, x2, v2, dim=3)["energy"] - inv0["energy"])

        x4, v4 = [list(p) for p in x], [list(q) for q in v]
        t = 0.0
        for _ in range(n):
            x4, v4, t, _ = LH.logh_yoshida4_step(
                m, x4, v4, dtau, dim=3, B=B, t=t
            )
        err4 = abs(P.invariants(m, x4, v4, dim=3)["energy"] - inv0["energy"])

        self.assertLess(err4, err2)


class Reversibility(unittest.TestCase):
    def test_forward_backward_approx(self):
        m, x, v = _circular_binary(dim=3)
        inv0 = P.invariants(m, x, v, dim=3)
        B = -inv0["energy"]
        dtau = 0.005
        xx, vv = [list(p) for p in x], [list(q) for q in v]
        t = 0.0
        n = 50
        for _ in range(n):
            xx, vv, t, _ = LH.logh_leapfrog_step(
                m, xx, vv, dtau, dim=3, B=B, t=t
            )
        for _ in range(n):
            xx, vv, t, _ = LH.logh_leapfrog_step(
                m, xx, vv, -dtau, dim=3, B=B, t=t
            )
        err = max(abs(xx[i][c] - x[i][c]) for i in range(2) for c in range(3))
        self.assertLess(err, 5e-3)


class MultiBody(unittest.TestCase):
    def test_three_body_energy_bounded(self):
        m, x, v = _three_body_randomish(dim=3)
        inv0 = P.invariants(m, x, v, dim=3)
        B = -inv0["energy"] if inv0["energy"] < 0 else 1.0
        xx, vv = [list(p) for p in x], [list(q) for q in v]
        t = 0.0
        for _ in range(300):
            xx, vv, t, info = LH.logh_leapfrog_step(
                m, xx, vv, 0.01, dim=3, B=B, t=t
            )
            self.assertTrue(info["converged"])
        inv1 = P.invariants(m, xx, vv, dim=3)
        self.assertTrue(abs(inv1["energy"]) < 10.0 * (abs(inv0["energy"]) + 1.0))


class LabWrapper(unittest.TestCase):
    def test_lab_signature(self):
        m, x, v = _circular_binary(dim=3)
        for name in ("logh_leapfrog", "logh_yoshida4"):
            fn = get_step(name)
            x2, v2 = fn(m, x, v, 0.01, dim=3)
            self.assertEqual(len(x2), 2)
            self.assertEqual(len(x2[0]), 3)


if __name__ == "__main__":
    unittest.main()
