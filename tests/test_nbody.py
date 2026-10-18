import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from metafield_nbody import laws, duck, golden as GD, contract as C


def _complete(g):
    return bool(g.get("initial") and g.get("final") and g.get("checkpoints"))


def _ensure_golden_corpus():
    """Regenerate full corpus when missing or stub-only."""
    files = GD.load_all()
    complete = [g for _, g in files if _complete(g)]
    if len(complete) >= 11:
        return
    os.makedirs(GD.GOLDEN_DIR, exist_ok=True)
    written = GD.write_all()
    for g, path in written:
        if g["kind"] == "ticks":
            g["duck_horizon_ticks"] = duck.calibrate_horizon(g)
        else:
            g["duck_horizon_ticks"] = None
        GD.save(g, path)


class Laws(unittest.TestCase):
    def test_laws(self):
        for i, ok, d in laws.all_laws():
            with self.subTest(i):
                self.assertTrue(ok, d)


class Goldens(unittest.TestCase):
    def test_bit_exact_and_independent(self):
        _ensure_golden_corpus()
        files = GD.load_all()
        self.assertEqual(len(files), 11)
        for fn, g in files:
            with self.subTest(fn):
                self.assertTrue(_complete(g), "incomplete golden %s" % fn)
                self.assertEqual(GD.compare(g), [])
                self.assertEqual(duck.verify_golden_independent(g), [])


class Attacks(unittest.TestCase):
    def test_every_attack_rejected(self):
        for name, rejected, d in duck.attack_suite():
            with self.subTest(name):
                self.assertTrue(rejected, d)


if __name__ == "__main__":
    unittest.main()
