import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from metafield_nbody import laws, duck, golden as GD, contract as C


class Laws(unittest.TestCase):
    def test_laws(self):
        for i, ok, d in laws.all_laws():
            with self.subTest(i):
                self.assertTrue(ok, d)


class Goldens(unittest.TestCase):
    def test_bit_exact_and_independent(self):
        files = GD.load_all()
        self.assertEqual(len(files), 11)
        for fn, g in files:
            with self.subTest(fn):
                self.assertEqual(GD.compare(g), [])
                self.assertEqual(duck.verify_golden_independent(g), [])


class Attacks(unittest.TestCase):
    def test_every_attack_rejected(self):
        for name, rejected, d in duck.attack_suite():
            with self.subTest(name):
                self.assertTrue(rejected, d)


if __name__ == "__main__":
    unittest.main()
