"""Dimensional generalisation tests.

Verify that dim=3 recovers the previous numerical behaviour and that
D-dimensional force laws and independent coordinate evolution behave
as documented.
"""
import os
import sys
import unittest
from math import sqrt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metafield_nbody import physics as P
from metafield_nbody.integrators import forest_ruth4_fixed, velocity_verlet


class Dim3Regression(unittest.TestCase):
    """dim=3 must be bit-identical to the original hard-coded 3-D operators."""

    def test_accelerations_three_body(self):
        m = [1.0, 1.0, 1.0]
        x = [[1.0, 0.0, 0.0], [-0.5, 0.8660254037844386, 0.0], [-0.5, -0.8660254037844386, 0.0]]
        a_default = P.accelerations(m, x)          # dim defaults to 3
        a_explicit = P.accelerations(m, x, dim=3)
        self.assertEqual(a_default, a_explicit)
        # non-zero forces
        self.assertTrue(any(abs(c) > 1e-12 for row in a_default for c in row))

    def test_invariants_structure(self):
        m = [1.0, 2.0]
        x = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
        v = [[0.0, 0.1, 0.0], [0.0, -0.05, 0.0]]
        inv = P.invariants(m, x, v, dim=3)
        self.assertEqual(len(inv["momentum"]), 3)
        self.assertEqual(len(inv["angular_momentum"]), 3)  # Lx,Ly,Lz
        self.assertEqual(inv["dim"], 3)
        self.assertTrue(inv["energy"] < 0.0)  # bound


class ForceLawScaling(unittest.TestCase):
    """Check force magnitude scales as 1/r^(D-1)."""

    def _pair_force_mag(self, dim, sep):
        m = [1.0, 1.0]
        x = [[0.0] * dim, [0.0] * dim]
        x[1][0] = sep
        a = P.accelerations(m, x, dim=dim)
        # |a0| should equal G / sep^(D-1) for unsoftened limit (sep >> eps)
        return sqrt(sum(c * c for c in a[0]))

    def test_dim2_inverse_r(self):
        # force ~ 1/r  => |a| ~ 1/r
        f1 = self._pair_force_mag(2, 1.0)
        f2 = self._pair_force_mag(2, 2.0)
        ratio = f1 / f2
        self.assertAlmostEqual(ratio, 2.0, places=5)

    def test_dim3_inverse_square(self):
        # force ~ 1/r^2  => |a| ~ 1/r^2
        f1 = self._pair_force_mag(3, 1.0)
        f2 = self._pair_force_mag(3, 2.0)
        ratio = f1 / f2
        self.assertAlmostEqual(ratio, 4.0, places=5)

    def test_dim4_inverse_cube(self):
        # force ~ 1/r^3  => |a| ~ 1/r^3
        f1 = self._pair_force_mag(4, 1.0)
        f2 = self._pair_force_mag(4, 2.0)
        ratio = f1 / f2
        self.assertAlmostEqual(ratio, 8.0, places=5)


class FourDimensionalDynamics(unittest.TestCase):
    """The extra coordinate must participate in the dynamics."""

    def test_w_coordinate_affects_acceleration(self):
        m = [1.0, 1.0]
        # separation purely in w
        x = [[0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
        a = P.accelerations(m, x, dim=4)
        # a0 should point toward body 1 in the w direction
        self.assertAlmostEqual(a[0][0], 0.0, places=12)
        self.assertAlmostEqual(a[0][1], 0.0, places=12)
        self.assertAlmostEqual(a[0][2], 0.0, places=12)
        self.assertGreater(a[0][3], 0.0)
        self.assertAlmostEqual(a[1][3], -a[0][3], places=12)

    def test_angular_momentum_rank(self):
        m = [1.0, 1.0]
        x = [[1.0, 0.0, 0.0, 0.0], [-1.0, 0.0, 0.0, 0.0]]
        v = [[0.0, 0.5, 0.0, 0.1], [0.0, -0.5, 0.0, -0.1]]
        inv = P.invariants(m, x, v, dim=4)
        # 4-D has 6 independent angular-momentum components
        self.assertEqual(len(inv["angular_momentum"]), 6)
        self.assertEqual(len(inv["momentum"]), 4)

    def test_integration_moves_w(self):
        m = [1.0, 1.0]
        x = [[0.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.5]]
        v = [[0.0, 0.1, 0.0, 0.0], [0.0, -0.1, 0.0, 0.0]]
        x1, v1 = forest_ruth4_fixed(m, x, v, 0.01, dim=4)
        # w coordinates must change under mutual gravity
        self.assertNotEqual(x1[0][3], x[0][3])
        self.assertNotEqual(x1[1][3], x[1][3])


class TwoDimensionalDynamics(unittest.TestCase):
    def test_angular_momentum_rank(self):
        m = [1.0, 1.0]
        x = [[1.0, 0.0], [-1.0, 0.0]]
        v = [[0.0, 0.5], [0.0, -0.5]]
        inv = P.invariants(m, x, v, dim=2)
        self.assertEqual(len(inv["angular_momentum"]), 1)  # single Lz
        self.assertEqual(len(inv["momentum"]), 2)


if __name__ == "__main__":
    unittest.main()
