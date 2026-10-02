"""Gravitational N-body operators.  OPERATOR ABI: IMMUTABLE once golden-pinned.

Operators here are pure functions: (state in) -> (state out), no hidden state,
no libm transcendental calls (only + - * / and sqrt, all IEEE-754 correctly
rounded), so results are bit-identical on any conforming platform.

Changing any function below requires bumping OPERATOR_VERSION and
regenerating tests/golden/ + operators.lock.json (see README).
"""
from math import sqrt, inf

OPERATOR_NAME = "forest_ruth4"
OPERATOR_VERSION = "1.0.0"

G = 1.0
SOFTENING = 1e-6
EPS2 = SOFTENING * SOFTENING
# 1/(2-2^(1/3)), correctly rounded from a 50-digit evaluation.
THETA = float.fromhex("0x1.59e8b6eb96338p+0")
W0 = 1.0 - 2.0 * THETA            # the (negative) middle leapfrog weight

DT_MIN = 1e-7
DT_MAX = 1e-2
ETA = 0.01


def accelerations(m, x):
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
            r2 = dx * dx + dy * dy + dz * dz + EPS2
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


def _leapfrog(m, x, v, h):
    """Drift-kick-drift leapfrog of size h; x, v are fresh lists (mutated)."""
    hh = 0.5 * h
    n = len(m)
    for i in range(n):
        xi, vi = x[i], v[i]
        xi[0] += hh * vi[0]; xi[1] += hh * vi[1]; xi[2] += hh * vi[2]
    a = accelerations(m, x)
    for i in range(n):
        xi, vi, ai = x[i], v[i], a[i]
        vi[0] += h * ai[0]; vi[1] += h * ai[1]; vi[2] += h * ai[2]
        xi[0] += hh * vi[0]; xi[1] += hh * vi[1]; xi[2] += hh * vi[2]


def forest_ruth4_step(m, x, v, h):
    """4th-order symplectic Forest-Ruth step = three leapfrogs
    (theta*h, (1-2*theta)*h, theta*h).  Returns new (x, v)."""
    x = [list(p) for p in x]
    v = [list(q) for q in v]
    _leapfrog(m, x, v, THETA * h)
    _leapfrog(m, x, v, W0 * h)
    _leapfrog(m, x, v, THETA * h)
    return x, v


def adaptive_dt(m, x, v, eta=ETA, dt_min=DT_MIN, dt_max=DT_MAX):
    """dt = eta * min over pairs of min(free-fall time, fly-by time)."""
    n = len(m)
    tmin = inf
    for i in range(n - 1):
        for j in range(i + 1, n):
            dx = x[j][0] - x[i][0]; dy = x[j][1] - x[i][1]; dz = x[j][2] - x[i][2]
            r2 = dx * dx + dy * dy + dz * dz + EPS2
            d = sqrt(r2)
            t_ff = sqrt(r2 * d / (G * (m[i] + m[j])))
            wx = v[j][0] - v[i][0]; wy = v[j][1] - v[i][1]; wz = v[j][2] - v[i][2]
            w2 = wx * wx + wy * wy + wz * wz
            t_fb = d / sqrt(w2) if w2 > 0.0 else inf
            tmin = min(tmin, t_ff, t_fb)
    dt = eta * tmin
    return min(dt_max, max(dt_min, dt))


def invariants(m, x, v):
    """Total energy (softened PE, consistent with the force), linear and
    angular momentum, plus mass and centre of mass."""
    n = len(m)
    ke = 0.0
    px = py = pz = 0.0
    lx = ly = lz = 0.0
    mt = 0.0
    cx = cy = cz = 0.0
    for i in range(n):
        mi = m[i]; xi = x[i]; vi = v[i]
        ke += 0.5 * mi * (vi[0] * vi[0] + vi[1] * vi[1] + vi[2] * vi[2])
        px += mi * vi[0]; py += mi * vi[1]; pz += mi * vi[2]
        lx += mi * (xi[1] * vi[2] - xi[2] * vi[1])
        ly += mi * (xi[2] * vi[0] - xi[0] * vi[2])
        lz += mi * (xi[0] * vi[1] - xi[1] * vi[0])
        mt += mi
        cx += mi * xi[0]; cy += mi * xi[1]; cz += mi * xi[2]
    pe = 0.0
    for i in range(n - 1):
        for j in range(i + 1, n):
            dx = x[j][0] - x[i][0]; dy = x[j][1] - x[i][1]; dz = x[j][2] - x[i][2]
            pe -= G * m[i] * m[j] / sqrt(dx * dx + dy * dy + dz * dz + EPS2)
    return {
        "kinetic": ke, "potential": pe, "energy": ke + pe,
        "momentum": [px, py, pz], "angular_momentum": [lx, ly, lz],
        "mass": mt, "com": [cx / mt, cy / mt, cz / mt],
    }
