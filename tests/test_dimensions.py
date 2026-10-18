"""Dimensional generalisation tests (physics_nd)."""
import os
import sys
import unittest
from math import sqrt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metafield_nbody import physics as P
from metafield_nbody import physics_nd as ND
from metafield_nbody.integrators import forest_ruth4_fixed


class Dim3Regression(unittest.TestCase):
    def test_accelerations_match_golden(self):
        m = [1.0, 1.0, 1.0]
        x = [[1.0, 0.0, 0.0], [-0.5, 0.8660254037844386, 0.0], [-0.5, -0.8660254037844386, 0.0]]
        self.assertEqual(ND.accelerations(m, x, dim=3), P.accelerations(m, x))

    def test_invariants_match_golden(self):
        m = [1.0, 2.0]
        x = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
        v = [[0.0, 0.1, 0.0], [0.0, -0.05, 0.0]]
        a = P.invariants(m, x, v)
        b = ND.invariants(m, x, v, dim=3)
        self.assertEqual(a["energy"], b["energy"])
        self.assertEqual(a["angular_momentum"], b["angular_momentum"])


class ForceLawScaling(unittest.TestCase):
    def _pair_force_mag(self, dim, sep):
        m = [1.0, 1.0]
        x = [[0.0] * dim, [0.0] * dim]
        x[1][0] = sep
        a = ND.accelerations(m, x, dim=dim)
        return sqrt(sum(c * c for c in a[0]))

    def test_dim2_inverse_r(self):
        f1 = self._pair_force_mag(2, 1.0)
        f2 = self._pair_force_mag(2, 2.0)
        self.assertAlmostEqual(f1 / f2, 2.0, places=5)

    def test_dim3_inverse_square(self):
        f1 = self._pair_force_mag(3, 1.0)
        f2 = self._pair_force_mag(3, 2.0)
        self.assertAlmostEqual(f1 / f2, 4.0, places=5)

    def test_dim4_inverse_cube(self):
        f1 = self._pair_force_mag(4, 1.0)
        f2 = self._pair_force_mag(4, 2.0)
        self.assertAlmostEqual(f1 / f2, 8.0, places=5)


class FourDimensionalDynamics(unittest.TestCase):
    def test_w_coordinate_affects_acceleration(self):
        m = [1.0, 1.0]
        x = [[0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
        a = ND.accelerations(m, x, dim=4)
        self.assertAlmostEqual(a[0][0], 0.0, places=12)
        self.assertGreater(a[0][3], 0.0)
        self.assertAlmostEqual(a[1][3], -a[0][3], places=12)

    def test_angular_momentum_rank(self):
        m = [1.0, 1.0]
        x = [[1.0, 0.0, 0.0, 0.0], [-1.0, 0.0, 0.0, 0.0]]
        v = [[0.0, 0.5, 0.0, 0.1], [0.0, -0.5, 0.0, -0.1]]
        inv = ND.invariants(m, x, v, dim=4)
        self.assertEqual(len(inv["angular_momentum"]), 6)

    def test_integration_moves_w(self):
        m = [1.0, 1.0]
        x = [[0.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.5]]
        v = [[0.0, 0.1, 0.0, 0.0], [0.0, -0.1, 0.0, 0.0]]
        x1, _ = forest_ruth4_fixed(m, x, v, 0.01, dim=4)
        self.assertNotEqual(x1[0][3], x[0][3])


class TwoDimensionalDynamics(unittest.TestCase):
    def test_angular_momentum_rank(self):
        m = [1.0, 1.0]
        x = [[1.0, 0.0], [-1.0, 0.0]]
        v = [[0.0, 0.5], [0.0, -0.5]]
        inv = ND.invariants(m, x, v, dim=2)
        self.assertEqual(len(inv["angular_momentum"]), 1)


if __name__ == "__main__":
    unittest.main()
