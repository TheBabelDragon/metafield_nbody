"""Golden corpus generation / bit-exact comparison (operator-ABI pattern).

A golden pins: initial state, per-50-tick chain digests + states, final state
(all floats as float.hex), invariants, and the operator version/source hash.
"""
import json
import os

from . import contract as C
from . import physics as P
from . import scenarios as S
from .field import NBodyField

GOLDEN_DIR = os.path.join(C.ROOT, "tests", "golden")
LOCK_PATH = os.path.join(C.ROOT, "operators.lock.json")
TICKS = 300
CHECK_EVERY = 50


def hx(v):
    if isinstance(v, (list, tuple)):
        return [hx(q) for q in v]
    return float(v).hex()


def unhx(v):
    if isinstance(v, list):
        return [unhx(q) for q in v]
    return float.fromhex(v)


def _state(f):
    return {"t": hx(f.t), "m": hx(f.m), "x": hx(f.x), "v": hx(f.v)}


def make_golden(key, kind="ticks"):
    f = NBodyField(key)
    init = _state(f)
    cps = []
    if kind == "ticks":
        for k in range(1, TICKS + 1):
            f.advance(1)
            if k % CHECK_EVERY == 0:
                cps.append({"tick": k, "digest": f.digest, "state": _state(f)})
        tag = "ticks%d" % TICKS
    else:                                       # 'third-period' (figure-8 law run)
        f.run_until(f.period / 3.0)
        cps.append({"tick": f.tick_no, "digest": f.digest, "state": _state(f)})
        tag = "third_period"
    inv = f.invariants()
    return {
        "golden_version": 1, "scenario": f.name, "key": f.key, "kind": kind, "tag": tag,
        "operator": {"name": P.OPERATOR_NAME, "version": P.OPERATOR_VERSION,
                     "src_sha256": C.operator_src_sha256()},
        "eta": f.eta, "initial": init, "checkpoints": cps,
        "final": {"tick": f.tick_no, "digest": f.digest, "state": _state(f),
                  "energy": hx(inv["energy"]), "momentum": hx(inv["momentum"]),
                  "angular_momentum": hx(inv["angular_momentum"])},
    }


def golden_path(g):
    return os.path.join(GOLDEN_DIR, "%s.%s.golden.json" % (g["scenario"], g["tag"]))


def corpus_spec():
    spec = [(rec[0], "ticks") for rec in S.SCENARIOS]
    spec.append(("1", "third"))
    return spec


def write_all():
    os.makedirs(GOLDEN_DIR, exist_ok=True)
    files = []
    for key, kind in corpus_spec():
        g = make_golden(key, kind)
        g["duck_horizon_ticks"] = None           # filled by duck.calibrate()
        files.append((g, golden_path(g)))
    return files


def save(g, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(g, fh, indent=1, sort_keys=True)
        fh.write("\n")


def load_all():
    out = []
    for fn in sorted(os.listdir(GOLDEN_DIR)):
        if fn.endswith(".golden.json"):
            with open(os.path.join(GOLDEN_DIR, fn), "r", encoding="utf-8") as fh:
                out.append((fn, json.load(fh)))
    return out


def file_sha(path):
    with open(path, "rb") as fh:
        return C.sha256_hex(fh.read())


def compare(g):
    """Bit-exact recompute with the primary operator.  Returns list of errors."""
    errs = []
    cur = make_golden(g["key"], g["kind"])
    if g["operator"] != cur["operator"]:
        errs.append("operator version/source hash differs from golden "
                    "(bump OPERATOR_VERSION and regenerate goldens)")
    if g["initial"] != cur["initial"]:
        errs.append("initial conditions differ from golden")
    if g["checkpoints"] != cur["checkpoints"]:
        errs.append("checkpoint digests/states differ")
    if g["final"] != cur["final"]:
        errs.append("final state/digest/invariants differ")
    return errs
