"""Logarithmic Hamiltonian (extended phase-space) adaptive symplectic integrator.

Uses physics_nd for force/potential so dim != 3 is supported.  Does not touch
the golden-pinned physics.py operators.
"""
from __future__ import annotations

from typing import List

from . import physics as P
from . import physics_nd as ND

_YOSHIDA_THETA = P.THETA
_YOSHIDA_W0 = P.W0


def _kinetic(m, v, dim):
    ke = 0.0
    for i in range(len(m)):
        s = 0.0
        for c in range(dim):
            s += v[i][c] * v[i][c]
        ke += 0.5 * m[i] * s
    return ke


def _potential(m, x, dim):
    inv = ND.invariants(m, x, [[0.0] * dim for _ in m], dim=dim)
    # ND.invariants with zero velocity gives pure potential
    return inv["potential"]


def logh_leapfrog_step(m, x, v, dtau, *, dim=3, B=None, t=0.0, eps_floor=1e-30):
    dim = int(dim)
    n = len(m)
    x = [list(p) for p in x]
    v = [list(q) for q in v]

    T = _kinetic(m, v, dim)
    U = _potential(m, x, dim)

    if B is None:
        E = T + U
        B = -E if E < 0.0 else 1.0
    B = float(B)

    denom_T = max(T + B, eps_floor)
    h_half = 0.5 * dtau / denom_T
    for i in range(n):
        for c in range(dim):
            x[i][c] += h_half * v[i][c]
    t = t + h_half

    U = _potential(m, x, dim)
    denom_U = max(-U, eps_floor)
    a = ND.accelerations(m, x, dim=dim)
    kick = dtau / denom_U
    for i in range(n):
        for c in range(dim):
            v[i][c] += kick * a[i][c]

    T = _kinetic(m, v, dim)
    denom_T = max(T + B, eps_floor)
    h_half = 0.5 * dtau / denom_T
    for i in range(n):
        for c in range(dim):
            x[i][c] += h_half * v[i][c]
    t = t + h_half

    info = {
        "dtau": dtau,
        "dt_physical_est": h_half * 2.0,
        "T": T,
        "U": U,
        "B": B,
        "converged": True,
        "dim": dim,
        "order": 2,
    }
    return x, v, t, info


def logh_yoshida4_step(m, x, v, dtau, *, dim=3, B=None, t=0.0, eps_floor=1e-30):
    dim = int(dim)
    x = [list(p) for p in x]
    v = [list(q) for q in v]
    if B is None:
        T = _kinetic(m, v, dim)
        U = _potential(m, x, dim)
        E = T + U
        B = -E if E < 0.0 else 1.0
    B = float(B)
    x, v, t, _ = logh_leapfrog_step(
        m, x, v, _YOSHIDA_THETA * dtau, dim=dim, B=B, t=t, eps_floor=eps_floor
    )
    x, v, t, _ = logh_leapfrog_step(
        m, x, v, _YOSHIDA_W0 * dtau, dim=dim, B=B, t=t, eps_floor=eps_floor
    )
    x, v, t, info = logh_leapfrog_step(
        m, x, v, _YOSHIDA_THETA * dtau, dim=dim, B=B, t=t, eps_floor=eps_floor
    )
    info = dict(info)
    info["dtau"] = dtau
    info["order"] = 4
    info["composition"] = "yoshida"
    return x, v, t, info


def logh_leapfrog(m, x, v, h, G=None, soft2=None, dim=3, B=None):
    x_new, v_new, _t, _info = logh_leapfrog_step(m, x, v, h, dim=dim, B=B)
    return x_new, v_new


def logh_yoshida4(m, x, v, h, G=None, soft2=None, dim=3, B=None):
    x_new, v_new, _t, _info = logh_yoshida4_step(m, x, v, h, dim=dim, B=B)
    return x_new, v_new
