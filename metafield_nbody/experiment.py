"""Experiment manifests, IC validation, lineage."""
from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from . import physics as P
from . import scenarios as S
from .integrators import INTEGRATORS

MANIFEST_VERSION = "1.0.0"
MAX_BODIES = 32
MAX_STEPS = 500000
MAX_DURATION = 1000.0
MIN_DT = 1e-9
MAX_DT = 1.0
MAX_MASS = 1e12
MAX_COORD = 1e6
MAX_SWEEP_SAMPLES = 64


class ValidationError(ValueError):
    pass


def _finite(x):
    try:
        return x == x and abs(x) != float("inf")
    except Exception:
        return False


def validate_bodies(m, x, v):
    if not isinstance(m, (list, tuple)) or not m:
        raise ValidationError("at least one body required")
    n = len(m)
    if n > MAX_BODIES:
        raise ValidationError("too many bodies")
    if len(x) != n or len(v) != n:
        raise ValidationError("m, x, v length mismatch")
    for i in range(n):
        if not _finite(m[i]) or m[i] <= 0:
            raise ValidationError("invalid mass at %d" % i)
        if len(x[i]) != 3 or len(v[i]) != 3:
            raise ValidationError("bad vector at %d" % i)
        for c in range(3):
            if not _finite(x[i][c]) or not _finite(v[i][c]):
                raise ValidationError("non-finite state at %d" % i)
            if abs(x[i][c]) > MAX_COORD or abs(v[i][c]) > MAX_COORD:
                raise ValidationError("coordinate out of range at %d" % i)
    for i in range(n - 1):
        for j in range(i + 1, n):
            dx = x[i][0] - x[j][0]
            dy = x[i][1] - x[j][1]
            dz = x[i][2] - x[j][2]
            if dx * dx + dy * dy + dz * dz < P.EPS2 * 0.25:
                raise ValidationError("bodies %d and %d nearly coincident" % (i, j))


def validate_run_params(dt, n_steps=None, duration=None, integrator_id=None):
    if not _finite(dt) or dt <= 0:
        raise ValidationError("dt must be > 0")
    if dt < MIN_DT or dt > MAX_DT:
        raise ValidationError("dt out of range")
    if integrator_id is not None and integrator_id not in INTEGRATORS:
        raise ValidationError("unknown integrator")
    if n_steps is not None and (not isinstance(n_steps, int) or n_steps < 1 or n_steps > MAX_STEPS):
        raise ValidationError("invalid n_steps")
    if duration is not None and (not _finite(duration) or duration <= 0 or duration > MAX_DURATION):
        raise ValidationError("invalid duration")


def bodies_from_scenario(sel):
    try:
        built = S.build(sel)
    except KeyError as exc:
        raise ValidationError("unknown scenario") from exc
    return {
        "source": "scenario",
        "scenario_key": built["key"],
        "scenario_name": built["name"],
        "m": built["m"],
        "x": built["x"],
        "v": built["v"],
        "note": built["note"],
        "experimental": False,
    }


def make_custom_ic(m, x, v, name="custom"):
    m = [float(mi) for mi in m]
    x = [[float(c) for c in p] for p in x]
    v = [[float(c) for c in q] for q in v]
    validate_bodies(m, x, v)
    return {
        "source": "custom",
        "scenario_key": None,
        "scenario_name": name,
        "m": m,
        "x": x,
        "v": v,
        "note": "user-defined experimental initial conditions",
        "experimental": True,
    }


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def config_digest(config):
    return hashlib.sha256(_canonical(config).encode("utf-8")).hexdigest()


def new_experiment_id():
    return uuid.uuid4().hex[:12]


def build_config(
    *,
    ic,
    integrator_id="forest_ruth4_fixed",
    dt=1e-3,
    n_steps=None,
    duration=None,
    G=None,
    softening=None,
    parent_id=None,
    changes=None,
    label="",
    seed=None,
):
    if G is None:
        G = P.G
    if softening is None:
        softening = P.SOFTENING
    validate_bodies(ic["m"], ic["x"], ic["v"])
    validate_run_params(dt, n_steps=n_steps, duration=duration, integrator_id=integrator_id)
    if n_steps is None and duration is None:
        n_steps = 1000
    if n_steps is None:
        n_steps = max(1, int(duration / dt))
    if n_steps > MAX_STEPS:
        raise ValidationError("n_steps too large")
    if not _finite(G) or G <= 0:
        raise ValidationError("invalid G")
    if not _finite(softening) or softening < 0:
        raise ValidationError("invalid softening")
    cfg = {
        "manifest_version": MANIFEST_VERSION,
        "experiment_id": new_experiment_id(),
        "label": label or ("exp-%s" % integrator_id),
        "created_unix": time.time(),
        "parent_id": parent_id,
        "changes_from_parent": list(changes or []),
        "ic": {
            "source": ic.get("source"),
            "scenario_key": ic.get("scenario_key"),
            "scenario_name": ic.get("scenario_name"),
            "experimental": bool(ic.get("experimental", True)),
            "m": ic["m"],
            "x": ic["x"],
            "v": ic["v"],
            "note": ic.get("note", ""),
        },
        "model": {"force": "softened_newtonian", "G": float(G), "softening": float(softening)},
        "integration": {
            "method": integrator_id,
            "method_name": INTEGRATORS[integrator_id]["name"],
            "symplectic": INTEGRATORS[integrator_id]["symplectic"],
            "order": INTEGRATORS[integrator_id]["order"],
            "dt": float(dt),
            "n_steps": int(n_steps),
            "duration": float(dt) * int(n_steps),
            "adaptive": False,
        },
        "seed": seed,
        "software": {
            "package": "metafield_nbody",
            "physics_operator": P.OPERATOR_NAME,
            "physics_operator_version": P.OPERATOR_VERSION,
            "lab_module": "experiment",
            "lab_manifest_version": MANIFEST_VERSION,
        },
    }
    cfg["config_digest"] = config_digest(
        {k: v for k, v in cfg.items() if k not in ("experiment_id", "created_unix", "config_digest")}
    )
    return cfg


def derive_config(parent, changes, label=""):
    ic = copy.deepcopy(parent["ic"])
    integration = copy.deepcopy(parent["integration"])
    model = copy.deepcopy(parent["model"])
    change_notes = []
    if "integrator_id" in changes:
        integration["method"] = changes["integrator_id"]
        change_notes.append("integrator changed")
    if "dt" in changes:
        integration["dt"] = float(changes["dt"])
        change_notes.append("dt changed")
    if "n_steps" in changes:
        integration["n_steps"] = int(changes["n_steps"])
        change_notes.append("n_steps changed")
    if "duration" in changes and "n_steps" not in changes:
        integration["n_steps"] = max(1, int(float(changes["duration"]) / integration["dt"]))
        change_notes.append("duration changed")
    if "G" in changes:
        model["G"] = float(changes["G"])
        change_notes.append("G changed")
    if "softening" in changes:
        model["softening"] = float(changes["softening"])
        change_notes.append("softening changed")
    if "ic" in changes:
        ic = changes["ic"]
        change_notes.append("ic replaced")
    if "m" in changes or "x" in changes or "v" in changes:
        ic = make_custom_ic(
            changes.get("m", ic["m"]),
            changes.get("x", ic["x"]),
            changes.get("v", ic["v"]),
            name=ic.get("scenario_name", "custom"),
        )
        change_notes.append("IC vectors modified")
    return build_config(
        ic=ic,
        integrator_id=integration["method"],
        dt=integration["dt"],
        n_steps=integration["n_steps"],
        G=model["G"],
        softening=model["softening"],
        parent_id=parent["experiment_id"],
        changes=change_notes,
        label=label or ("derived-from-%s" % parent["experiment_id"]),
        seed=parent.get("seed"),
    )


def diff_configs(a, b):
    diffs = []
    pairs = [
        ("integration.method", a["integration"]["method"], b["integration"]["method"]),
        ("integration.dt", a["integration"]["dt"], b["integration"]["dt"]),
        ("integration.n_steps", a["integration"]["n_steps"], b["integration"]["n_steps"]),
        ("model.G", a["model"]["G"], b["model"]["G"]),
        ("model.softening", a["model"]["softening"], b["model"]["softening"]),
    ]
    for path, va, vb in pairs:
        if va != vb:
            diffs.append("%s: %r -> %r" % (path, va, vb))
    if a["ic"]["m"] != b["ic"]["m"] or a["ic"]["x"] != b["ic"]["x"] or a["ic"]["v"] != b["ic"]["v"]:
        diffs.append("ic bodies differ")
    return diffs
