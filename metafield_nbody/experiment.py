"""Experiment manifests, initial-condition validation, and lineage.

Lab experiments are separate from NBodyField FieldTick emission. Each run
records a versioned manifest so results can be inspected, compared, and
reproduced without mutating historical provenance.
"""
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
MAX_STEPS = 500_000
MAX_DURATION = 1000.0
MIN_DT = 1e-9
MAX_DT = 1.0
MAX_MASS = 1e12
MAX_COORD = 1e6
MAX_SWEEP_SAMPLES = 64


class ValidationError(ValueError):
    """Invalid experimental configuration — never silently repaired."""


def _finite(x) -> bool:
    try:
        return x == x and abs(x) != float("inf")
    except Exception:
        return False


def validate_bodies(m, x, v) -> None:
    if not isinstance(m, (list, tuple)) or not m:
        raise ValidationError("at least one body required")
    n = len(m)
    if n > MAX_BODIES:
        raise ValidationError("at most %d bodies allowed (got %d)" % (MAX_BODIES, n))
    if len(x) != n or len(v) != n:
        raise ValidationError("m, x, v length mismatch")
    for i in range(n):
        if not _finite(m[i]) or m[i] <= 0:
            raise ValidationError("body %d: mass must be finite and > 0 (got %r)" % (i, m[i]))
        if m[i] > MAX_MASS:
            raise ValidationError("body %d: mass exceeds MAX_MASS=%g" % (i, MAX_MASS))
        if len(x[i]) != 3 or len(v[i]) != 3:
            raise ValidationError("body %d: position/velocity must be 3-vectors" % i)
        for c, label in enumerate("xyz"):
            if not _finite(x[i][c]) or abs(x[i][c]) > MAX_COORD:
                raise ValidationError(
                    "body %d: position %s invalid or out of range" % (i, label)
                )
            if not _finite(v[i][c]) or abs(v[i][c]) > MAX_COORD:
                raise ValidationError(
                    "body %d: velocity %s invalid or out of range" % (i, label)
                )
    for i in range(n - 1):
        for j in range(i + 1, n):
            dx = x[i][0] - x[j][0]
            dy = x[i][1] - x[j][1]
            dz = x[i][2] - x[j][2]
            r2 = dx * dx + dy * dy + dz * dz
            if r2 < P.EPS2 * 0.25:
                raise ValidationError(
                    "bodies %d and %d are nearly coincident (singular configuration)"
                    % (i, j)
                )


def validate_run_params(dt, n_steps=None, duration=None, integrator_id=None) -> None:
    if not _finite(dt) or dt <= 0:
        raise ValidationError("dt must be finite and > 0")
    if dt < MIN_DT or dt > MAX_DT:
        raise ValidationError("dt must be in [%g, %g]" % (MIN_DT, MAX_DT))
    if integrator_id is not None and integrator_id not in INTEGRATORS:
        raise ValidationError("unknown integrator %r" % integrator_id)
    if n_steps is not None:
        if not isinstance(n_steps, int) or n_steps < 1:
            raise ValidationError("n_steps must be a positive integer")
        if n_steps > MAX_STEPS:
            raise ValidationError("n_steps exceeds MAX_STEPS=%d" % MAX_STEPS)
    if duration is not None:
        if not _finite(duration) or duration <= 0:
            raise ValidationError("duration must be finite and > 0")
        if duration > MAX_DURATION:
            raise ValidationError("duration exceeds MAX_DURATION=%g" % MAX_DURATION)


def bodies_from_scenario(sel) -> Dict[str, Any]:
    try:
        built = S.build(sel)
    except KeyError as exc:
        raise ValidationError("unknown scenario %r" % sel) from exc
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


def make_custom_ic(m, x, v, name: str = "custom") -> Dict[str, Any]:
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


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def config_digest(config: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(config).encode("utf-8")).hexdigest()


def new_experiment_id() -> str:
    return uuid.uuid4().hex[:12]


def build_config(
    *,
    ic: Dict[str, Any],
    integrator_id: str = "forest_ruth4_fixed",
    dt: float = 1e-3,
    n_steps: Optional[int] = None,
    duration: Optional[float] = None,
    G: float = P.G,
    softening: float = P.SOFTENING,
    parent_id: Optional[str] = None,
    changes: Optional[List[str]] = None,
    label: str = "",
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    validate_bodies(ic["m"], ic["x"], ic["v"])
    validate_run_params(dt, n_steps=n_steps, duration=duration, integrator_id=integrator_id)
    if n_steps is None and duration is None:
        n_steps = 1000
    if n_steps is None:
        n_steps = max(1, int(duration / dt))
    if n_steps > MAX_STEPS:
        raise ValidationError("resolved n_steps=%d exceeds MAX_STEPS=%d" % (n_steps, MAX_STEPS))
    if not _finite(G) or G <= 0:
        raise ValidationError("G must be finite and > 0")
    if not _finite(softening) or softening < 0:
        raise ValidationError("softening must be finite and >= 0")

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
        "model": {
            "force": "softened_newtonian",
            "G": float(G),
            "softening": float(softening),
        },
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


def derive_config(parent: Dict[str, Any], changes: Dict[str, Any], label: str = "") -> Dict[str, Any]:
    ic = copy.deepcopy(parent["ic"])
    integration = copy.deepcopy(parent["integration"])
    model = copy.deepcopy(parent["model"])
    change_notes = []

    if "integrator_id" in changes:
        integration["method"] = changes["integrator_id"]
        change_notes.append("integrator -> %s" % changes["integrator_id"])
    if "dt" in changes:
        integration["dt"] = float(changes["dt"])
        change_notes.append("dt -> %g" % changes["dt"])
    if "n_steps" in changes:
        integration["n_steps"] = int(changes["n_steps"])
        change_notes.append("n_steps -> %d" % changes["n_steps"])
    if "duration" in changes and "n_steps" not in changes:
        integration["n_steps"] = max(1, int(float(changes["duration"]) / integration["dt"]))
        change_notes.append("duration -> %g" % changes["duration"])
    if "G" in changes:
        model["G"] = float(changes["G"])
        change_notes.append("G -> %g" % changes["G"])
    if "softening" in changes:
        model["softening"] = float(changes["softening"])
        change_notes.append("softening -> %g" % changes["softening"])
    if "ic" in changes:
        ic = changes["ic"]
        change_notes.append("initial conditions replaced")
    if "m" in changes or "x" in changes or "v" in changes:
        m = changes.get("m", ic["m"])
        x = changes.get("x", ic["x"])
        v = changes.get("v", ic["v"])
        ic = make_custom_ic(m, x, v, name=ic.get("scenario_name", "custom"))
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


def diff_configs(a: Dict[str, Any], b: Dict[str, Any]) -> List[str]:
    diffs = []
    for path, va, vb in (
        ("integration.method", a["integration"]["method"], b["integration"]["method"]),
        ("integration.dt", a["integration"]["dt"], b["integration"]["dt"]),
        ("integration.n_steps", a["integration"]["n_steps"], b["integration"]["n_steps"]),
        ("model.G", a["model"]["G"], b["model"]["G"]),
        ("model.softening", a["model"]["softening"], b["model"]["softening"]),
        ("ic.source", a["ic"]["source"], b["ic"]["source"]),
        ("ic.scenario_key", a["ic"].get("scenario_key"), b["ic"].get("scenario_key")),
    ):
        if va != vb:
            diffs.append("%s: %r -> %r" % (path, va, vb))
    if a["ic"]["m"] != b["ic"]["m"] or a["ic"]["x"] != b["ic"]["x"] or a["ic"]["v"] != b["ic"]["v"]:
        diffs.append("ic bodies: mass/position/velocity differ")
    return diffs
