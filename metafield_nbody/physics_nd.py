"""Dimension-parameterised gravitational operators (D = 2, 3, 4, …).

This module is used by the laboratory / experimental path.  The golden-pinned
FieldTick operator remains in physics.py and must not import from here.

When dim == 3, results match physics.py (same formulae; may differ by at most
loop structure, not used for FieldTick digests).
"""
from math import sqrt, log

from . import physics as P

G = P.G
EPS2 = P.EPS2
THETA = P.THETA
W0 = P.W0


def _force_factor(r2s, dim):
    if dim == 3:
        return G / (r2s * sqrt(r2s))
    if dim == 2:
        return G / r2s
    if dim == 4:
        return G / (r2s * r2s)
    return G / (r2s ** (0.5 * (dim - 1)))


def _pair_potential(r2s, dim):
    if dim == 3:
        return 1.0 / sqrt(r2s)
    if dim == 2:
        return 0.5 * log(r2s)
    if dim == 4:
        return 1.0 / r2s
    return r2s ** (0.5 * (2 - dim)) / (dim - 2)


def accelerations(m, x, dim=3):
    dim = int(dim)
    if dim == 3:
        return P.accelerations(m, x)
    n = len(m)
    a = [[0.0] * dim for _ in range(n)]
    for i in range(n - 1):
        xi = x[i]
        ai = a[i]
        for j in range(i + 1, n):
            xj = x[j]
            r2 = EPS2
            dx = [0.0] * dim
            for c in range(dim):
                d = xj[c] - xi[c]
                dx[c] = d
                r2 += d * d
            f = _force_factor(r2, dim)
            fi = f * m[j]
            fj = f * m[i]
            aj = a[j]
            for c in range(dim):
                ai[c] += fi * dx[c]
                aj[c] -= fj * dx[c]
    return a


def forest_ruth4_step(m, x, v, h, dim=3):
    dim = int(dim)
    if dim == 3:
        return P.forest_ruth4_step(m, x, v, h)
    x = [list(p) for p in x]
    v = [list(q) for q in v]

    def leap(hh_scale):
        hh = 0.5 * hh_scale
        n = len(m)
        for i in range(n):
            for c in range(dim):
                x[i][c] += hh * v[i][c]
        a = accelerations(m, x, dim=dim)
        for i in range(n):
            for c in range(dim):
                v[i][c] += hh_scale * a[i][c]
                x[i][c] += hh * v[i][c]

    leap(THETA * h)
    leap(W0 * h)
    leap(THETA * h)
    return x, v


def invariants(m, x, v, dim=3):
    dim = int(dim)
    if dim == 3:
        inv = P.invariants(m, x, v)
        inv["dim"] = 3
        return inv
    n = len(m)
    ke = 0.0
    p = [0.0] * dim
    n_ang = dim * (dim - 1) // 2
    L = [0.0] * n_ang
    mt = 0.0
    com = [0.0] * dim
    for i in range(n):
        mi = m[i]
        xi, vi = x[i], v[i]
        v2 = 0.0
        for c in range(dim):
            v2 += vi[c] * vi[c]
            p[c] += mi * vi[c]
            com[c] += mi * xi[c]
        ke += 0.5 * mi * v2
        mt += mi
        k = 0
        for c0 in range(dim):
            for c1 in range(c0 + 1, dim):
                L[k] += mi * (xi[c0] * vi[c1] - xi[c1] * vi[c0])
                k += 1
    if mt:
        com = [c / mt for c in com]
    pe = 0.0
    for i in range(n - 1):
        for j in range(i + 1, n):
            r2 = EPS2
            for c in range(dim):
                d = x[j][c] - x[i][c]
                r2 += d * d
            pe -= G * m[i] * m[j] * _pair_potential(r2, dim)
    return {
        "kinetic": ke,
        "potential": pe,
        "energy": ke + pe,
        "momentum": p,
        "angular_momentum": L,
        "mass": mt,
        "com": com,
        "dim": dim,
    }
