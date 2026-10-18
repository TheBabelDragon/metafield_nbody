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
    """Two equal masses on a circular relative orbit of radius a."""
    m = [1.0, 1.0]
    # reduced mass mu = 0.5; omega^2 = G(m1+m2)/a^3 = 2/a^3
    omega = sqrt(2.0 / (a * a * a))
    x = [[0.0] * dim for _ in range(2)]
    v = [[0.0] * dim for _ in range(2)]
    x[0][0] = -0.5 * a
    x[1][0] = 0.5 * a
    v[0][1] = -0.5 * omega * a
    v[1][1] = 0.5 * omega * a
    return m, x, v


class Registry(unittest.TestCase):
    def test_registered(self):
        ids = [e["id"] for e in list_integrators()]
        self.assertIn("logh_leapfrog", ids)
        fn = get_step("logh_leapfrog")
        self.assertTrue(callable(fn))


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
        # energy should remain negative (bound) and not explode
        self.assertLess(inv1["energy"], 0.0)
        rel = abs(inv1["energy"] - inv0["energy"]) / abs(inv0["energy"])
        self.assertLess(rel, 0.05)  # generous bound for 2nd-order over many steps

    def test_physical_time_advances(self):
        m, x, v = _circular_binary(dim=3)
        inv0 = P.invariants(m, x, v, dim=3)
        B = -inv0["energy"]
        xx, vv, t, info = LH.logh_leapfrog_step(
            m, x, v, 0.05, dim=3, B=B, t=0.0
        )
        self.assertGreater(t, 0.0)

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


class LabWrapper(unittest.TestCase):
    def test_lab_signature(self):
        m, x, v = _circular_binary(dim=3)
        fn = get_step("logh_leapfrog")
        x2, v2 = fn(m, x, v, 0.01, dim=3)
        self.assertEqual(len(x2), 2)
        self.assertEqual(len(x2[0]), 3)


if __name__ == "__main__":
    unittest.main()
