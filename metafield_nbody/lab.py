"""Interactive Dynamics Laboratory — isolated experiment execution.

Runs use integrators.py (fixed-step). They do not share mutable state with
the live NBodyField / VizSession and do not emit FieldTicks by default.

Long work (sweeps) runs on a background thread with cancellation and limits.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from . import experiment as E
from .integrators import get_step, invariants as lab_invariants

SAMPLE_STRIDE = 10


class Cancelled(Exception):
    pass


def _energy_series(history):
    if not history:
        return {
            "E0": None, "E_final": None, "abs_diff": None, "rel_drift": None,
            "max_abs_drift": None, "mean_abs_drift": None,
            "t": [], "energy": [], "rel_drift_series": [],
        }
    E0 = history[0]["energy"]
    energies = [h["energy"] for h in history]
    ts = [h["t"] for h in history]
    abs_diffs = [abs(e - E0) for e in energies]
    denom = abs(E0) if abs(E0) > 1e-30 else 1.0
    rel = [d / denom for d in abs_diffs]
    return {
        "E0": E0,
        "E_final": energies[-1],
        "abs_diff": abs(energies[-1] - E0),
        "rel_drift": rel[-1],
        "max_abs_drift": max(abs_diffs),
        "mean_abs_drift": sum(abs_diffs) / len(abs_diffs),
        "t": ts,
        "energy": energies,
        "rel_drift_series": rel,
    }


def run_experiment(
    config,
    *,
    sample_stride=SAMPLE_STRIDE,
    record_trajectories=True,
    cancel_event=None,
    progress_cb=None,
):
    cfg = copy.deepcopy(config)
    ic = cfg["ic"]
    m = [float(x) for x in ic["m"]]
    x = [list(p) for p in ic["x"]]
    v = [list(q) for q in ic["v"]]
    E.validate_bodies(m, x, v)

    method = cfg["integration"]["method"]
    dt = float(cfg["integration"]["dt"])
    n_steps = int(cfg["integration"]["n_steps"])
    G = float(cfg["model"]["G"])
    soft2 = float(cfg["model"]["softening"]) ** 2
    step_fn = get_step(method)

    inv0 = lab_invariants(m, x, v, G=G, soft2=soft2)
    history = [{
        "t": 0.0,
        "step": 0,
        "energy": inv0["energy"],
        "momentum": inv0["momentum"],
        "angular_momentum": inv0["angular_momentum"],
        "x": [list(p) for p in x] if record_trajectories else None,
        "v": [list(q) for q in v] if record_trajectories else None,
    }]

    t = 0.0
    status = "completed"
    error_msg = None
    t0 = time.monotonic()

    try:
        for s in range(1, n_steps + 1):
            if cancel_event is not None and cancel_event.is_set():
                status = "cancelled"
                raise Cancelled()
            x, v = step_fn(m, x, v, dt, G=G, soft2=soft2)
            t += dt
            for i in range(len(m)):
                for c in range(3):
                    if not (x[i][c] == x[i][c] and v[i][c] == v[i][c]):
                        raise FloatingPointError("non-finite state at step %d" % s)
            if s % sample_stride == 0 or s == n_steps:
                inv = lab_invariants(m, x, v, G=G, soft2=soft2)
                history.append({
                    "t": t,
                    "step": s,
                    "energy": inv["energy"],
                    "momentum": inv["momentum"],
                    "angular_momentum": inv["angular_momentum"],
                    "x": [list(p) for p in x] if record_trajectories else None,
                    "v": [list(q) for q in v] if record_trajectories else None,
                })
            if progress_cb and (s % max(1, n_steps // 20) == 0):
                progress_cb(s / n_steps)
    except Cancelled:
        pass
    except Exception as exc:
        status = "failed"
        error_msg = "%s: %s" % (type(exc).__name__, exc)

    inv_f = lab_invariants(m, x, v, G=G, soft2=soft2)
    drift = _energy_series(history)
    wall = time.monotonic() - t0

    trails = None
    if record_trajectories:
        trails = [[] for _ in m]
        for h in history:
            if h["x"] is None:
                continue
            for i, p in enumerate(h["x"]):
                trails[i].append(p)

    result = {
        "manifest_version": E.MANIFEST_VERSION,
        "experiment_id": cfg["experiment_id"],
        "config": cfg,
        "status": status,
        "error": error_msg,
        "wall_seconds": wall,
        "initial_invariants": inv0,
        "final_invariants": inv_f,
        "energy_analysis": {
            "E0": drift["E0"],
            "E_final": drift["E_final"],
            "abs_diff": drift["abs_diff"],
            "rel_drift": drift["rel_drift"],
            "max_abs_drift": drift["max_abs_drift"],
            "mean_abs_drift": drift["mean_abs_drift"],
            "note": (
                "Relative drift is |E(t)-E0|/|E0|. Bounded oscillation is typical "
                "for symplectic methods; secular growth indicates non-symplectic "
                "drift or instability. Energy conservation alone does not prove "
                "trajectory accuracy."
            ),
        },
        "series": {
            "t": drift["t"],
            "energy": drift["energy"],
            "rel_drift": drift["rel_drift_series"],
        },
        "final_state": {"m": m, "x": [list(p) for p in x], "v": [list(q) for q in v]},
        "trails": trails,
        "sample_stride": sample_stride,
    }
    digest_payload = {
        "config_digest": cfg.get("config_digest"),
        "status": status,
        "final_energy": inv_f["energy"],
        "rel_drift": drift["rel_drift"],
        "n_samples": len(history),
    }
    result["run_digest"] = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return result


def compare_experiments(results):
    if len(results) < 2:
        raise ValueError("need at least two results to compare")
    configs = [r["config"] for r in results]
    diffs = []
    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            d = E.diff_configs(configs[i], configs[j])
            diffs.append({
                "a": results[i]["experiment_id"],
                "b": results[j]["experiment_id"],
                "differences": d,
            })
    return {
        "experiments": [
            {
                "id": r["experiment_id"],
                "label": r["config"].get("label"),
                "method": r["config"]["integration"]["method"],
                "dt": r["config"]["integration"]["dt"],
                "n_steps": r["config"]["integration"]["n_steps"],
                "rel_drift": r["energy_analysis"]["rel_drift"],
                "max_abs_drift": r["energy_analysis"]["max_abs_drift"],
                "status": r["status"],
                "run_digest": r["run_digest"],
            }
            for r in results
        ],
        "pairwise_diffs": diffs,
    }


def trajectory_separation(a, b):
    if not a.get("trails") or not b.get("trails"):
        raise ValueError("both results need recorded trajectories")
    na, nb = len(a["trails"]), len(b["trails"])
    n = min(na, nb)
    seps = []
    ta = a["series"]["t"]
    tb = b["series"]["t"]
    n_samples = min(len(ta), len(tb), min(len(a["trails"][i]) for i in range(n)))
    for k in range(n_samples):
        dmax = 0.0
        dsum = 0.0
        for i in range(n):
            pa = a["trails"][i][k]
            pb = b["trails"][i][k]
            d = math.sqrt(sum((pa[c] - pb[c]) ** 2 for c in range(3)))
            dmax = max(dmax, d)
            dsum += d
        seps.append({
            "t": 0.5 * (ta[k] + tb[k]),
            "mean_sep": dsum / n,
            "max_sep": dmax,
        })
    return {
        "kind": "numerical_comparison",
        "note": (
            "Separation between corresponding bodies at aligned sample times. "
            "Not a verified Lyapunov exponent; not a proof of chaos."
        ),
        "n_samples": n_samples,
        "series": seps,
        "final_max_sep": seps[-1]["max_sep"] if seps else None,
        "final_mean_sep": seps[-1]["mean_sep"] if seps else None,
    }


class LabStore:
    def __init__(self):
        self._lock = threading.RLock()
        self.experiments = {}
        self.configs = {}
        self._sweep_thread = None
        self._sweep_cancel = threading.Event()
        self._sweep_status = {"active": False}

    def list_experiments(self):
        with self._lock:
            out = []
            for eid, r in self.experiments.items():
                out.append({
                    "experiment_id": eid,
                    "label": r["config"].get("label"),
                    "status": r["status"],
                    "method": r["config"]["integration"]["method"],
                    "dt": r["config"]["integration"]["dt"],
                    "rel_drift": r["energy_analysis"].get("rel_drift"),
                    "parent_id": r["config"].get("parent_id"),
                    "run_digest": r.get("run_digest"),
                })
            return out

    def get(self, experiment_id):
        with self._lock:
            return copy.deepcopy(self.experiments.get(experiment_id))

    def run(self, config, **kwargs):
        result = run_experiment(config, **kwargs)
        with self._lock:
            self.configs[config["experiment_id"]] = copy.deepcopy(config)
            self.experiments[config["experiment_id"]] = result
        return result

    def derive_and_run(self, parent_id, changes, label=""):
        with self._lock:
            parent = self.configs.get(parent_id) or (
                self.experiments[parent_id]["config"] if parent_id in self.experiments else None
            )
        if parent is None:
            raise KeyError("unknown parent experiment %r" % parent_id)
        cfg = E.derive_config(parent, changes, label=label)
        return self.run(cfg)

    def start_sweep(self, *, base_config, parameter, values, label_prefix="sweep"):
        if self._sweep_status.get("active"):
            raise RuntimeError("a sweep is already running")
        if len(values) > E.MAX_SWEEP_SAMPLES:
            raise E.ValidationError("at most %d sweep samples" % E.MAX_SWEEP_SAMPLES)
        if not values:
            raise E.ValidationError("sweep values empty")

        self._sweep_cancel.clear()
        self._sweep_status = {
            "active": True,
            "parameter": parameter,
            "total": len(values),
            "completed": 0,
            "failed": 0,
            "results": [],
            "error": None,
        }

        def worker():
            try:
                for i, val in enumerate(values):
                    if self._sweep_cancel.is_set():
                        break
                    changes = {parameter: val}
                    cfg = E.derive_config(
                        base_config, changes,
                        label="%s-%s=%g" % (label_prefix, parameter, val),
                    )
                    try:
                        result = run_experiment(
                            cfg,
                            cancel_event=self._sweep_cancel,
                            record_trajectories=False,
                        )
                        with self._lock:
                            self.configs[cfg["experiment_id"]] = cfg
                            self.experiments[cfg["experiment_id"]] = result
                            self._sweep_status["results"].append({
                                "experiment_id": cfg["experiment_id"],
                                "value": val,
                                "rel_drift": result["energy_analysis"]["rel_drift"],
                                "status": result["status"],
                            })
                            if result["status"] == "failed":
                                self._sweep_status["failed"] += 1
                    except Exception as exc:
                        with self._lock:
                            self._sweep_status["failed"] += 1
                            self._sweep_status["results"].append({
                                "value": val,
                                "status": "failed",
                                "error": str(exc),
                            })
                    with self._lock:
                        self._sweep_status["completed"] = i + 1
            except Exception as exc:
                with self._lock:
                    self._sweep_status["error"] = str(exc)
            finally:
                with self._lock:
                    self._sweep_status["active"] = False

        self._sweep_thread = threading.Thread(target=worker, daemon=True)
        self._sweep_thread.start()
        return {"ok": True, "status": dict(self._sweep_status)}

    def cancel_sweep(self):
        self._sweep_cancel.set()
        return {"ok": True}

    def sweep_status(self):
        with self._lock:
            return copy.deepcopy(self._sweep_status)


def default_lab_ic(scenario="1"):
    return E.bodies_from_scenario(scenario)
