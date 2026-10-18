"""Gravitational N-body operators.  OPERATOR ABI: IMMUTABLE once golden-pinned.

Operators here are pure functions: (state in) -> (state out), no hidden state,
no libm transcendental calls (only + - * / and sqrt, all IEEE-754 correctly
rounded), so results are bit-identical on any conforming platform.

Changing any function below requires bumping OPERATOR_VERSION and
regenerating tests/golden/ + operators.lock.json (see README).

Dimensional generalisation (2026-10-18)
---------------------------------------
All operators accept an optional ``dim`` keyword (default 3).  When
dim == 3 the arithmetic sequence is identical to the pre-generalisation
code, so existing FieldTick digests and golden files remain valid.
Supported values: 2, 3, 4 (higher dimensions work mathematically but
are not yet covered by the scenario / test suite).

Force-law convention (D-dimensional Gauss law):
  force magnitude scales as 1 / r^(D-1)
  potential scales as r^(2-D) for D != 2, logarithmic for D = 2.
With Plummer softening the practical force factor is
  f = G / r2s**((D-1)/2)
which recovers the classic G/(r2*sqrt(r2)) expression for D = 3.
"""
from math import sqrt, inf, log

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

SUPPORTED_DIMS = (2, 3, 4)


def _validate_dim(dim):
    d = int(dim)
    if d < 1:
        raise ValueError("dim must be >= 1, got %r" % (dim,))
    return d


def _force_factor(r2s, dim):
    """Return the scalar f such that a_i += f * m_j * (x_j - x_i).

    For dim == 3 this is exactly G / (r2s * sqrt(r2s)), matching the
    original golden-pinned expression instruction-for-instruction.
    """
    if dim == 3:
        return G / (r2s * sqrt(r2s))
    if dim == 2:
        return G / r2s
    if dim == 4:
        return G / (r2s * r2s)
    return G / (r2s ** (0.5 * (dim - 1)))


def _pair_potential(r2s, dim):
    """Softened pairwise potential factor (positive; caller applies sign/G*m*m).

    For dim == 3 returns 1/sqrt(r2s).  Callers that need bit-identical
    3-D results should use the dedicated dim==3 PE path in invariants().
    """
    if dim == 3:
        return 1.0 / sqrt(r2s)
    if dim == 2:
        return 0.5 * log(r2s)
    if dim == 4:
        return 1.0 / r2s
    return r2s ** (0.5 * (2 - dim)) / (dim - 2)


def accelerations(m, x, dim=3):
    """Pairwise softened accelerations in ``dim`` spatial dimensions."""
    dim = _validate_dim(dim)
    n = len(m)
    if dim == 3:
        # Bit-identical path to OPERATOR_VERSION 1.0.0
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


def _leapfrog(m, x, v, h, dim=3):
    """Drift-kick-drift leapfrog of size h; x, v are fresh lists (mutated)."""
    dim = _validate_dim(dim)
    hh = 0.5 * h
    n = len(m)
    if dim == 3:
        for i in range(n):
            xi, vi = x[i], v[i]
            xi[0] += hh * vi[0]; xi[1] += hh * vi[1]; xi[2] += hh * vi[2]
        a = accelerations(m, x, dim=3)
        for i in range(n):
            xi, vi, ai = x[i], v[i], a[i]
            vi[0] += h * ai[0]; vi[1] += h * ai[1]; vi[2] += h * ai[2]
            xi[0] += hh * vi[0]; xi[1] += hh * vi[1]; xi[2] += hh * vi[2]
        return
    for i in range(n):
        xi, vi = x[i], v[i]
        for c in range(dim):
            xi[c] += hh * vi[c]
    a = accelerations(m, x, dim=dim)
    for i in range(n):
        xi, vi, ai = x[i], v[i], a[i]
        for c in range(dim):
            vi[c] += h * ai[c]
            xi[c] += hh * vi[c]


def forest_ruth4_step(m, x, v, h, dim=3):
    """4th-order symplectic Forest-Ruth step = three leapfrogs
    (theta*h, (1-2*theta)*h, theta*h).  Returns new (x, v).

    ``dim`` defaults to 3; when dim==3 the arithmetic is bit-identical
    to OPERATOR_VERSION 1.0.0.
    """
    dim = _validate_dim(dim)
    x = [list(p) for p in x]
    v = [list(q) for q in v]
    _leapfrog(m, x, v, THETA * h, dim=dim)
    _leapfrog(m, x, v, W0 * h, dim=dim)
    _leapfrog(m, x, v, THETA * h, dim=dim)
    return x, v


def adaptive_dt(m, x, v, eta=ETA, dt_min=DT_MIN, dt_max=DT_MAX, dim=3):
    """dt = eta * min over pairs of min(free-fall time, fly-by time)."""
    dim = _validate_dim(dim)
    n = len(m)
    tmin = inf
    if dim == 3:
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
    else:
        for i in range(n - 1):
            for j in range(i + 1, n):
                r2 = EPS2
                for c in range(dim):
                    d = x[j][c] - x[i][c]
                    r2 += d * d
                d = sqrt(r2)
                t_ff = sqrt(r2 * d / (G * (m[i] + m[j])))
                w2 = 0.0
                for c in range(dim):
                    w = v[j][c] - v[i][c]
                    w2 += w * w
                t_fb = d / sqrt(w2) if w2 > 0.0 else inf
                tmin = min(tmin, t_ff, t_fb)
    dt = eta * tmin
    return min(dt_max, max(dt_min, dt))


def invariants(m, x, v, dim=3):
    """Total energy (softened PE consistent with the force), linear and
    angular momentum, mass and centre of mass.

    For dim == 3 the return layout matches the original golden-pinned API:
    angular_momentum = [Lx, Ly, Lz] with the classic cross-product components.
    For dim != 3, angular_momentum is the list of independent antisymmetric
    tensor components ordered by pairs (c0, c1) with 0 <= c0 < c1 < dim.
    """
    dim = _validate_dim(dim)
    n = len(m)

    if dim == 3:
        # Exact original path — bit-identical to OPERATOR_VERSION 1.0.0
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
            "dim": 3,
        }

    ke = 0.0
    p = [0.0] * dim
    n_ang = dim * (dim - 1) // 2
    L = [0.0] * n_ang
    mt = 0.0
    com = [0.0] * dim
    for i in range(n):
        mi = m[i]
        xi = x[i]
        vi = v[i]
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
