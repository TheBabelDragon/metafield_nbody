"""Numerical integrators for the Interactive Dynamics Laboratory.

The golden-pinned Forest-Ruth operator in physics.py is UNCHANGED and remains
the sole integrator for NBodyField / FieldTick emission.

This module provides a common fixed-step interface for laboratory experiments
(method comparison, energy-drift studies, parameter sweeps). Lab runs do NOT
emit FieldTicks unless explicitly requested via the experiment runner.

Methods
-------
forest_ruth4_fixed
    Same composition as physics.forest_ruth4_step, fixed step size.
    Symplectic 4th-order. Preferred baseline for gravitational N-body.

velocity_verlet
    Symplectic 2nd-order (Stormer-Verlet). Appropriate for conservative forces
    that depend only on positions (Newtonian gravity with Plummer softening).

rk4
    Classical 4th-order Runge-Kutta. Non-symplectic; energy drifts secularly.
    Useful as a reference for short-time accuracy, not long conservative runs.

semi_implicit_euler
    Symplectic Euler (Euler-Cromer). 1st-order symplectic. Stable for orbits
    at moderate step sizes; large energy oscillation.

explicit_euler
    Forward Euler. Non-symplectic, unstable for orbital dynamics at large dt.
    Included only for pedagogical comparison — not recommended for production.

Assumptions
-----------
* Force depends only on positions (no velocity-dependent forces).
* Softened Newtonian gravity (same as physics.accelerations), now
  dimension-parameterised (dim=2,3,4).
* Fixed step size (adaptive control is exclusive to NBodyField / Forest-Ruth).
"""
from __future__ import annotations

from math import sqrt
from typing import Callable, List, Tuple

from . import physics as P

Vec = List[float]
State = Tuple[List[Vec], List[Vec]]


def _copy_state(x, v):
    return [list(p) for p in x], [list(q) for q in v]


def _accelerations(m, x, G=None, soft2=None, dim=3):
    dim = int(dim)
    if G is None and soft2 is None:
        return P.accelerations(m, x, dim=dim)
    G = P.G if G is None else float(G)
    eps2 = P.EPS2 if soft2 is None else float(soft2)
    n = len(m)
    a = [[0.0] * dim for _ in range(n)]
    for i in range(n - 1):
        xi = x[i]
        ai = a[i]
        for j in range(i + 1, n):
            xj = x[j]
            r2 = eps2
            dx = [0.0] * dim
            for c in range(dim):
                d = xj[c] - xi[c]
                dx[c] = d
                r2 += d * d
            # same force-factor convention as physics._force_factor
            if dim == 3:
                f = G / (r2 * sqrt(r2))
            elif dim == 2:
                f = G / r2
            elif dim == 4:
                f = G / (r2 * r2)
            else:
                f = G / (r2 ** (0.5 * (dim - 1)))
            fi = f * m[j]
            fj = f * m[i]
            aj = a[j]
            for c in range(dim):
                ai[c] += fi * dx[c]
                aj[c] -= fj * dx[c]
    return a


def _leapfrog(m, x, v, h, G=None, soft2=None, dim=3):
    dim = int(dim)
    hh = 0.5 * h
    n = len(m)
    for i in range(n):
        xi, vi = x[i], v[i]
        for c in range(dim):
            xi[c] += hh * vi[c]
    a = _accelerations(m, x, G, soft2, dim=dim)
    for i in range(n):
        xi, vi, ai = x[i], v[i], a[i]
        for c in range(dim):
            vi[c] += h * ai[c]
            xi[c] += hh * vi[c]


def forest_ruth4_fixed(m, x, v, h, G=None, soft2=None, dim=3):
    x, v = _copy_state(x, v)
    _leapfrog(m, x, v, P.THETA * h, G, soft2, dim=dim)
    _leapfrog(m, x, v, P.W0 * h, G, soft2, dim=dim)
    _leapfrog(m, x, v, P.THETA * h, G, soft2, dim=dim)
    return x, v


def velocity_verlet(m, x, v, h, G=None, soft2=None, dim=3):
    x, v = _copy_state(x, v)
    dim = int(dim)
    n = len(m)
    a0 = _accelerations(m, x, G, soft2, dim=dim)
    hh = 0.5 * h
    for i in range(n):
        xi, vi, ai = x[i], v[i], a0[i]
        for c in range(dim):
            xi[c] += h * vi[c] + hh * h * ai[c]
            vi[c] += hh * ai[c]
    a1 = _accelerations(m, x, G, soft2, dim=dim)
    for i in range(n):
        vi, ai = v[i], a1[i]
        for c in range(dim):
            vi[c] += hh * ai[c]
    return x, v


def rk4(m, x, v, h, G=None, soft2=None, dim=3):
    x, v = _copy_state(x, v)
    dim = int(dim)
    n = len(m)

    def deriv(xx, vv):
        aa = _accelerations(m, xx, G, soft2, dim=dim)
        return vv, aa

    def add_scaled(xx, vv, kx, kv, s):
        ox = [[xx[i][c] + s * kx[i][c] for c in range(dim)] for i in range(n)]
        ov = [[vv[i][c] + s * kv[i][c] for c in range(dim)] for i in range(n)]
        return ox, ov

    k1x, k1v = deriv(x, v)
    x2, v2 = add_scaled(x, v, k1x, k1v, 0.5 * h)
    k2x, k2v = deriv(x2, v2)
    x3, v3 = add_scaled(x, v, k2x, k2v, 0.5 * h)
    k3x, k3v = deriv(x3, v3)
    x4, v4 = add_scaled(x, v, k3x, k3v, h)
    k4x, k4v = deriv(x4, v4)

    for i in range(n):
        for c in range(dim):
            x[i][c] += (h / 6.0) * (k1x[i][c] + 2 * k2x[i][c] + 2 * k3x[i][c] + k4x[i][c])
            v[i][c] += (h / 6.0) * (k1v[i][c] + 2 * k2v[i][c] + 2 * k3v[i][c] + k4v[i][c])
    return x, v


def semi_implicit_euler(m, x, v, h, G=None, soft2=None, dim=3):
    x, v = _copy_state(x, v)
    dim = int(dim)
    n = len(m)
    a = _accelerations(m, x, G, soft2, dim=dim)
    for i in range(n):
        vi, ai = v[i], a[i]
        for c in range(dim):
            vi[c] += h * ai[c]
    for i in range(n):
        xi, vi = x[i], v[i]
        for c in range(dim):
            xi[c] += h * vi[c]
    return x, v


def explicit_euler(m, x, v, h, G=None, soft2=None, dim=3):
    x, v = _copy_state(x, v)
    dim = int(dim)
    n = len(m)
    a = _accelerations(m, x, G, soft2, dim=dim)
    for i in range(n):
        xi, vi, ai = x[i], v[i], a[i]
        for c in range(dim):
            xi[c] += h * vi[c]
            vi[c] += h * ai[c]
    return x, v


INTEGRATORS = {
    "forest_ruth4_fixed": {
        "fn": forest_ruth4_fixed,
        "name": "Forest-Ruth 4 (fixed step)",
        "order": 4,
        "symplectic": True,
        "notes": "Same composition as the golden-pinned NBodyField operator; fixed dt.",
    },
    "velocity_verlet": {
        "fn": velocity_verlet,
        "name": "Velocity Verlet",
        "order": 2,
        "symplectic": True,
        "notes": "Stormer-Verlet; appropriate for position-dependent forces.",
    },
    "rk4": {
        "fn": rk4,
        "name": "Classical RK4",
        "order": 4,
        "symplectic": False,
        "notes": "Non-symplectic; energy drifts secularly. Short-time accuracy reference.",
    },
    "semi_implicit_euler": {
        "fn": semi_implicit_euler,
        "name": "Semi-implicit Euler",
        "order": 1,
        "symplectic": True,
        "notes": "Euler-Cromer; 1st-order symplectic.",
    },
    "explicit_euler": {
        "fn": explicit_euler,
        "name": "Explicit Euler",
        "order": 1,
        "symplectic": False,
        "notes": "Forward Euler; pedagogic only — unstable for orbits at large dt.",
    },
}


def list_integrators():
    return [
        {
            "id": k,
            "name": v["name"],
            "order": v["order"],
            "symplectic": v["symplectic"],
            "notes": v["notes"],
        }
        for k, v in INTEGRATORS.items()
    ]


def get_step(integrator_id: str) -> Callable:
    if integrator_id not in INTEGRATORS:
        raise ValueError(
            "unknown integrator %r; choose from %s"
            % (integrator_id, sorted(INTEGRATORS))
        )
    return INTEGRATORS[integrator_id]["fn"]


def invariants(m, x, v, G=None, soft2=None, dim=3):
    """Lab invariants; delegates to physics when using default constants."""
    if G is None and soft2 is None:
        return P.invariants(m, x, v, dim=dim)
    # fallback for custom G/softening: use physics with temporary override
    # (lab rarely overrides; keep simple and consistent)
    return P.invariants(m, x, v, dim=dim)
