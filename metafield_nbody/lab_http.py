"""Lab HTTP helpers mounted by viz.VizHandler."""
from __future__ import annotations

import json
from urllib.parse import parse_qs

from . import experiment as E
from . import lab as Lab
from . import physics as P
from .integrators import list_integrators


def handle_lab_get(handler, path, parsed):
    if path == "/api/lab/integrators":
        handler._json(200, {"integrators": list_integrators()})
        return True
    if path == "/api/lab/experiments":
        handler._json(200, {"experiments": handler.lab.list_experiments()})
        return True
    if path == "/api/lab/experiment":
        qs = parse_qs(parsed.query)
        eid = (qs.get("id") or [""])[0]
        r = handler.lab.get(eid)
        if r is None:
            handler._json(404, {"ok": False, "msg": "unknown experiment"})
        else:
            include = (qs.get("include") or [""])[0]
            if include != "trails" and r.get("trails"):
                r = dict(r)
                r["trails"] = None
                r["trails_omitted"] = True
            handler._json(200, {"ok": True, "result": r})
        return True
    if path == "/api/lab/sweep_status":
        handler._json(200, handler.lab.sweep_status())
        return True
    return False


def _summary(result):
    out = dict(result)
    if out.get("trails") is not None:
        out["trail_points"] = sum(len(t) for t in out["trails"])
        out["trails"] = None
        out["trails_omitted"] = True
    return out


def _lab_run(handler, data):
    if data.get("config"):
        cfg = data["config"]
    else:
        if data.get("ic_custom"):
            ic = E.make_custom_ic(
                data["ic_custom"]["m"],
                data["ic_custom"]["x"],
                data["ic_custom"]["v"],
                name=data["ic_custom"].get("name", "custom"),
            )
        else:
            ic = Lab.default_lab_ic(data.get("scenario", "1"))
        cfg = E.build_config(
            ic=ic,
            integrator_id=data.get("integrator_id", "forest_ruth4_fixed"),
            dt=float(data.get("dt", 1e-3)),
            n_steps=int(data.get("n_steps", 1000)),
            duration=data.get("duration"),
            G=float(data.get("G", P.G)),
            softening=float(data.get("softening", P.SOFTENING)),
            label=data.get("label") or "",
            parent_id=data.get("parent_id"),
            changes=data.get("changes"),
        )
    return handler.lab.run(
        cfg,
        record_trajectories=bool(data.get("record_trajectories", True)),
        sample_stride=int(data.get("sample_stride", Lab.SAMPLE_STRIDE)),
    )


def handle_lab_post(handler, path, data):
    if path == "/api/lab/run":
        try:
            result = _lab_run(handler, data)
            handler._json(200, {"ok": True, "result": _summary(result)})
        except Exception as exc:
            handler._json(400, {"ok": False, "msg": str(exc)})
        return True
    if path == "/api/lab/derive":
        try:
            result = handler.lab.derive_and_run(
                data["parent_id"], data.get("changes") or {},
                label=data.get("label") or "",
            )
            handler._json(200, {"ok": True, "result": _summary(result)})
        except Exception as exc:
            handler._json(400, {"ok": False, "msg": str(exc)})
        return True
    if path == "/api/lab/compare":
        try:
            ids = data.get("ids") or []
            results = []
            for eid in ids:
                r = handler.lab.get(eid)
                if r is None:
                    raise KeyError("unknown experiment %r" % eid)
                results.append(r)
            handler._json(200, {"ok": True, "comparison": Lab.compare_experiments(results)})
        except Exception as exc:
            handler._json(400, {"ok": False, "msg": str(exc)})
        return True
    if path == "/api/lab/sweep":
        try:
            base = data.get("config")
            if not base:
                if data.get("ic_custom"):
                    ic = E.make_custom_ic(
                        data["ic_custom"]["m"],
                        data["ic_custom"]["x"],
                        data["ic_custom"]["v"],
                        name=data["ic_custom"].get("name", "custom"),
                    )
                else:
                    ic = Lab.default_lab_ic(data.get("scenario", "1"))
                base = E.build_config(
                    ic=ic,
                    integrator_id=data.get("integrator_id", "forest_ruth4_fixed"),
                    dt=float(data.get("dt", 1e-3)),
                    n_steps=int(data.get("n_steps", 1000)),
                    G=float(data.get("G", P.G)),
                    softening=float(data.get("softening", P.SOFTENING)),
                    label=data.get("label") or "sweep-base",
                )
            out = handler.lab.start_sweep(
                base_config=base,
                parameter=data["parameter"],
                values=[float(v) for v in data["values"]],
                label_prefix=data.get("label_prefix", "sweep"),
            )
            handler._json(200, out)
        except Exception as exc:
            handler._json(400, {"ok": False, "msg": str(exc)})
        return True
    if path == "/api/lab/sweep_cancel":
        handler._json(200, handler.lab.cancel_sweep())
        return True
    if path == "/api/lab/validate_ic":
        try:
            E.validate_bodies(data["m"], data["x"], data["v"])
            handler._json(200, {"ok": True})
        except Exception as exc:
            handler._json(200, {"ok": False, "msg": str(exc)})
        return True
    if path == "/api/lab/ic_from_scenario":
        try:
            ic = E.bodies_from_scenario(data.get("scenario", "1"))
            handler._json(200, {"ok": True, "ic": ic})
        except Exception as exc:
            handler._json(400, {"ok": False, "msg": str(exc)})
        return True
    return False
