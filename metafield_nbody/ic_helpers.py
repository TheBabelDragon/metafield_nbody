"""Helpers for constructing dimension-aware initial conditions.

Scenarios remain 3-D for FieldTick compatibility. These helpers are intended
for lab experiments and custom configs where dim may be 2 or 4.
"""
from __future__ import annotations

from math import sqrt
from typing import List, Tuple

from . import experiment as E


def circular_binary(dim=3, a=1.0, m1=1.0, m2=1.0):
    """Equal-or-unequal mass circular binary in the x–y plane of R^dim."""
    dim = int(dim)
    if dim < 2:
        raise ValueError("dim must be >= 2")
    mtot = m1 + m2
    mu = m1 * m2 / mtot
    # omega^2 = G * mtot / a^3  (G=1)
    omega = sqrt(mtot / (a * a * a))
    r1 = a * m2 / mtot
    r2 = a * m1 / mtot
    x = [[0.0] * dim for _ in range(2)]
    v = [[0.0] * dim for _ in range(2)]
    x[0][0] = -r1
    x[1][0] = r2
    v[0][1] = -omega * r1
    v[1][1] = omega * r2
    return E.make_custom_ic([m1, m2], x, v, name="circular-binary-D%d" % dim, dim=dim)


def pad_to_dim(bodies_3d, dim):
    """Pad a 3-D IC (m,x,v lists) to higher dim with zeros, or truncate to 2."""
    m, x, v = bodies_3d["m"], bodies_3d["x"], bodies_3d["v"]
    dim = int(dim)
    if dim == 3:
        return E.make_custom_ic(m, x, v, name=bodies_3d.get("scenario_name", "padded"), dim=3)
    xx, vv = [], []
    for i in range(len(m)):
        pi = list(x[i][:dim]) + [0.0] * max(0, dim - len(x[i]))
        qi = list(v[i][:dim]) + [0.0] * max(0, dim - len(v[i]))
        xx.append(pi[:dim])
        vv.append(qi[:dim])
    return E.make_custom_ic(
        m, xx, vv,
        name="%s-D%d" % (bodies_3d.get("scenario_name", "ic"), dim),
        dim=dim,
    )
