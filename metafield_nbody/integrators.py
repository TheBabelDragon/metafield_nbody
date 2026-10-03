"""Numerical integrators for the Interactive Dynamics Laboratory.\n\nThe golden-pinned Forest-Ruth operator in physics.py is UNCHANGED and remains\nthe sole integrator for NBodyField / FieldTick emission.\n\nThis module provides a common fixed-step interface for laboratory experiments\n(method comparison, energy-drift studies, parameter sweeps). Lab runs do NOT\nemit FieldTicks unless explicitly requested via the experiment runner.\n\nMethods\n-------\nforest_ruth4_fixed\n    Same composition as physics.forest_ruth4_step, fixed step size.\n    Symplectic 4th-order. Preferred baseline for gravitational N-body.\n\nvelocity_verlet\n    Symplectic 2nd-order (Stormer-Verlet). Appropriate for conservative forces\n    that depend only on positions (Newtonian gravity with Plummer softening).\n\nrk4\n    Classical 4th-order Runge-Kutta. Non-symplectic; energy drifts secularly.\n    Useful as a reference for short-time accuracy, not long conservative runs.\n\nsemi_implicit_euler\n    Symplectic Euler (Euler-Cromer). 1st-order symplectic. Stable for orbits\n    at moderate step sizes; large energy oscillation.\n\nexplicit_euler\n    Forward Euler. Non-symplectic, unstable for orbital dynamics at large dt.\n    Included only for pedagogical comparison — not recommended for production.\n\nAssumptions\n-----------\n* Force depends only on positions (no velocity-dependent forces).\n* Softened Newtonian gravity (same as physics.accelerations).\n* Fixed step size (adaptive control is exclusive to NBodyField / Forest-Ruth).\n"""
from __future__ import annotations

from math import sqrt
from typing import Callable, List, Tuple

from . import physics as P

Vec3 = List[float]
State = Tuple[List[Vec3], List[Vec3]]


def _copy_state(x, v):
    return [list(p) for p in x], [list(q) for q in v]


def _accelerations(m, x, G=None, soft2=None):
    if G is None and soft2 is None:
        return P.accelerations(m, x)
    G = P.G if G is None else float(G)
    eps2 = P.EPS2 if soft2 is None else float(soft2)
    n = len(m)
    a = [[0.0, 0.0, 0.0] for _ in range(n)]
    for i in range(n - 1):
        xi = x[i]
        ai = a[i]
        for j in range(i + 1, n):
            xj = x[j]
            dx = xj[0] - xi[0]
            dy = xj[1] - xi[1]
            dz = xj[2] - xi[2]
            r2 = dx * dx + dy * dy + dz * dz + eps2
            f = G / (r2 * sqrt(r2))
            fi = f * m[j]
            fj = f * m[i]
            aj = a[j]
            ai[0] += fi * dx
            ai[1] += fi * dy
            ai[2] += fi * dz
            aj[0] -= fj * dx
            aj[1] -= fj * dy
            aj[2] -= fj * dz
    return a


def _leapfrog(m, x, v, h, G=None, soft2=None):
    hh = 0.5 * h
    n = len(m)
    for i in range(n):
        xi, vi = x[i], v[i]
        xi[0] += hh * vi[0]
        xi[1] += hh * vi[1]
        xi[2] += hh * vi[2]
    a = _accelerations(m, x, G, soft2)
    for i in range(n):
        xi, vi, ai = x[i], v[i], a[i]
        vi[0] += h * ai[0]
        vi[1] += h * ai[1]
        vi[2] += h * ai[2]
        xi[0] += hh * vi[0]
        xi[1] += hh * vi[1]
        xi[2] += hh * vi[2]


def forest_ruth4_fixed(m, x, v, h, G=None, soft2=None):
    x, v = _copy_state(x, v)
    _leapfrog(m, x, v, P.THETA * h, G, soft2)
    _leapfrog(m, x, v, P.W0 * h, G, soft2)
    _leapfrog(m, x, v, P.THETA * h, G, soft2)
    return x, v


def velocity_verlet(m, x, v, h, G=None, soft2=None):
    x, v = _copy_state(x, v)
    n = len(m)
    a0 = _accelerations(m, x, G, soft2)
    hh = 0.5 * h
    for i in range(n):
        xi, vi, ai = x[i], v[i], a0[i]
        xi[0] += h * vi[0] + hh * h * ai[0]
        xi[1] += h * vi[1] + hh * h * ai[1]
        xi[2] += h * vi[2] + hh * h * ai[2]
        vi[0] += hh * ai[0]
        vi[1] += hh * ai[1]
        vi[2] += hh * ai[2]
    a1 = _accelerations(m, x, G, soft2)
    for i in range(n):
        vi, ai = v[i], a1[i]
        vi[0] += hh * ai[0]
        vi[1] += hh * ai[1]
        vi[2] += hh * ai[2]
    return x, v


def rk4(m, x, v, h, G=None, soft2=None):
    x, v = _copy_state(x, v)
    n = len(m)

    def deriv(xx, vv):
        aa = _accelerations(m, xx, G, soft2)
        return vv, aa

    def add_scaled(xx, vv, kx, kv, s):
        ox = [[xx[i][c] + s * kx[i][c] for c in range(3)] for i in range(n)]
        ov = [[vv[i][c] + s * kv[i][c] for c in range(3)] for i in range(n)]
        return ox, ov

    k1x, k1v = deriv(x, v)
    x2, v2 = add_scaled(x, v, k1x, k1v, 0.5 * h)
    k2x, k2v = deriv(x2, v2)
    x3, v3 = add_scaled(x, v, k2x, k2v, 0.5 * h)
    k3x, k3v = deriv(x3, v3)
    x4, v4 = add_scaled(x, v, k3x, k3v, h)
    k4x, k4v = deriv(x4, v4)

    for i in range(n):
        for c in range(3):
            x[i][c] += (h / 6.0) * (k1x[i][c] + 2 * k2x[i][c] + 2 * k3x[i][c] + k4x[i][c])
            v[i][c] += (h / 6.0) * (k1v[i][c] + 2 * k2v[i][c] + 2 * k3v[i][c] + k4v[i][c])
    return x, v


def semi_implicit_euler(m, x, v, h, G=None, soft2=None):
    x, v = _copy_state(x, v)
    n = len(m)
    a = _accelerations(m, x, G, soft2)
    for i in range(n):
        vi, ai = v[i], a[i]
        vi[0] += h * ai[0]
        vi[1] += h * ai[1]
        vi[2] += h * ai[2]
    for i in range(n):
        xi, vi = x[i], v[i]
        xi[0] += h * vi[0]
        xi[1] += h * vi[1]
        xi[2] += h * vi[2]
    return x, v


def explicit_euler(m, x, v, h, G=None, soft2=None):
    x, v = _copy_state(x, v)
    n = len(m)
    a = _accelerations(m, x, G, soft2)
    for i in range(n):
        xi, vi, ai = x[i], v[i], a[i]
        xi[0] += h * vi[0]
        xi[1] += h * vi[1]
        xi[2] += h * vi[2]
        vi[0] += h * ai[0]
        vi[1] += h * ai[1]
        vi[2] += h * ai[2]
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


def invariants(m, x, v, G=None, soft2=None):
    G = P.G if G is None else float(G)
    eps2 = P.EPS2 if soft2 is None else float(soft2)
    n = len(m)
    ke = 0.0
    pe = 0.0
    px = py = pz = 0.0
    lx = ly = lz = 0.0
    mx = my = mz = 0.0
    mtot = 0.0
    for i in range(n):
        mi = m[i]
        xi, yi, zi = x[i]
        vxi, vyi, vzi = v[i]
        ke += 0.5 * mi * (vxi * vxi + vyi * vyi + vzi * vzi)
        px += mi * vxi
        py += mi * vyi
        pz += mi * vzi
        lx += mi * (yi * vzi - zi * vyi)
        ly += mi * (zi * vxi - xi * vzi)
        lz += mi * (xi * vyi - yi * vxi)
        mx += mi * xi
        my += mi * yi
        mz += mi * zi
        mtot += mi
        for j in range(i + 1, n):
            dx = x[j][0] - xi
            dy = x[j][1] - yi
            dz = x[j][2] - zi
            r = sqrt(dx * dx + dy * dy + dz * dz + eps2)
            pe -= G * mi * m[j] / r
    com = [mx / mtot, my / mtot, mz / mtot] if mtot else [0.0, 0.0, 0.0]
    return {
        "energy": ke + pe,
        "kinetic": ke,
        "potential": pe,
        "momentum": [px, py, pz],
        "angular_momentum": [lx, ly, lz],
        "mass": mtot,
        "com": com,
    }
