"""Independent verification entry point.

  python -m metafield_nbody.checker                 # run everything
  python -m metafield_nbody.checker --regen         # regenerate goldens+lock (version bump workflow)
  python -m metafield_nbody.checker --schema-dir ../field-os/schema   # validate against locked field-os schemas
"""
import argparse
import json
import os
import sys

from . import contract as C
from . import golden as GD
from . import duck, laws
from .field import NBodyField


def regen():
    files = GD.write_all()
    for g, path in files:
        if g["kind"] == "ticks":
            g["duck_horizon_ticks"] = duck.calibrate_horizon(g)
        else:
            g["duck_horizon_ticks"] = 0
        GD.save(g, path)
    lock = {"operator": {"name": "forest_ruth4", "version": files[0][0]["operator"]["version"],
                         "src_sha256": files[0][0]["operator"]["src_sha256"]},
            "goldens": {os.path.basename(p): GD.file_sha(p) for _, p in files}}
    with open(GD.LOCK_PATH, "w", encoding="utf-8") as fh:
        json.dump(lock, fh, indent=1, sort_keys=True); fh.write("\n")
    print("regenerated %d goldens + operators.lock.json" % len(files))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="metafield_nbody.checker")
    ap.add_argument("--regen", action="store_true")
    ap.add_argument("--schema-dir")
    ap.add_argument("--skip-attacks", action="store_true")
    args = ap.parse_args(argv)
    if args.regen:
        regen()
        return 0

    rows = []   # (section, id, ok, detail)

    def add(sec, i, ok, d=""):
        rows.append((sec, i, bool(ok), d))

    # 1. operator lock (immutability)
    with open(GD.LOCK_PATH, "r", encoding="utf-8") as fh:
        lock = json.load(fh)
    add("lock", "operator source hash + version match operators.lock.json",
        lock["operator"]["src_sha256"] == C.operator_src_sha256()
        and lock["operator"]["version"] == __import__("metafield_nbody.physics", fromlist=["x"]).OPERATOR_VERSION)
    for fn, g in GD.load_all():
        add("lock", "golden file unmodified: " + fn,
            lock["goldens"].get(fn) == GD.file_sha(os.path.join(GD.GOLDEN_DIR, fn)))

    # 2. goldens: bit-exact primary + independent recompute
    for fn, g in GD.load_all():
        e = GD.compare(g)
        add("golden", "bit-exact: " + fn, not e, "; ".join(e))
        e2 = duck.verify_golden_independent(g)
        add("duck", "independent recompute (%s ticks): %s" % (g.get("duck_horizon_ticks"), fn),
            not e2, "; ".join(e2))

    # 3. schema compliance of a sample from every scenario (optionally against locked field-os schemas)
    schemas = C.SchemaSet(args.schema_dir)
    from . import scenarios as S
    for rec in S.SCENARIOS:
        f = NBodyField(rec[0], schemas=schemas); f.advance(25)
        e = C.check_log(f.log, schemas)
        add("schema", "%s admitted by %s" % (rec[1], schemas.dir), not e, "; ".join(e)[:200])

    # 4. laws
    for i, ok, d in laws.all_laws():
        add("law", i, ok, d)

    # 5. attacks
    if not args.skip_attacks:
        for name, rejected, d in duck.attack_suite():
            add("attack", "rejected: " + name, rejected, d)

    bad = 0
    for sec, i, ok, d in rows:
        print("%-6s %s %s%s" % (sec, "PASS" if ok else "FAIL", i, ("  [" + d + "]") if d and (not ok or sec == "law") else ""))
        bad += (not ok)
    print("\n%d checks, %d failed" % (len(rows), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
