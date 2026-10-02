"""Hard-coded scenarios.  Selectable by key '1'..'9','0' or by name.

All constructions use only + - * / sqrt (no trig / pow) so initial
conditions are bit-identical everywhere.  Equal-mass 'Suvakov-Dmitrasinovic'
families: x1=-x2=(-1,0), x3=0, v1=v2=(vx,vy), v3=-2(vx,vy), m=1, G=1.
"""
from math import sqrt

_M64 = (1 << 64) - 1


def _splitmix64(state):
    state = (state + 0x9E3779B97F4A7C15) & _M64
    z = state
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _M64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _M64
    return state, z ^ (z >> 31)


def _uniform_stream(seed):
    s = seed & _M64
    while True:
        s, z = _splitmix64(s)
        yield (z >> 11) * (1.0 / 9007199254740992.0)


def _com_frame(m, x, v):
    mt = 0.0
    for mi in m:
        mt += mi
    cx = [0.0] * 3
    cv = [0.0] * 3
    for i in range(len(m)):
        for k in range(3):
            cx[k] += m[i] * x[i][k]
            cv[k] += m[i] * v[i][k]
    cx = [c / mt for c in cx]
    cv = [c / mt for c in cv]
    x = [[x[i][k] - cx[k] for k in range(3)] for i in range(len(m))]
    v = [[v[i][k] - cv[k] for k in range(3)] for i in range(len(m))]
    return x, v


def _sd(vx, vy):
    return ([1.0, 1.0, 1.0],
            [[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
            [[vx, vy, 0.0], [vx, vy, 0.0], [-2.0 * vx, -2.0 * vy, 0.0]])


def _figure8():
    # Chenciner-Montgomery / Simo.  Momentum and COM exactly zero in floats.
    a, b = 0.97000436, -0.24308753
    wx, wy = -0.93240737, -0.86473146
    x = [[a, b, 0.0], [-a, -b, 0.0], [0.0, 0.0, 0.0]]
    v = [[-0.5 * wx, -0.5 * wy, 0.0], [-0.5 * wx, -0.5 * wy, 0.0], [wx, wy, 0.0]]
    return [1.0, 1.0, 1.0], x, v


def _lagrange():
    s3 = sqrt(3.0)
    h = 1.0 / s3                      # circumradius of unit-side triangle
    pos = [[0.0, h, 0.0], [-0.5, -0.5 * h, 0.0], [0.5, -0.5 * h, 0.0]]
    w = s3                            # omega^2 = G*Mtot/a^3 = 3
    vel = [[-w * p[1], w * p[0], 0.0] for p in pos]
    vel[0][0] += 1e-3                 # fixed kick: Lagrange triangle (equal
    vel[0][1] += 5e-4                 # masses) is unstable -> chaos
    x, v = _com_frame([1.0, 1.0, 1.0], pos, vel)
    return [1.0, 1.0, 1.0], x, v


def _burrau():
    m = [3.0, 4.0, 5.0]
    x = [[1.0, 3.0, 0.0], [-2.0, -1.0, 0.0], [1.0, -1.0, 0.0]]
    v = [[0.0, 0.0, 0.0] for _ in range(3)]
    x, v = _com_frame(m, x, v)        # COM already at origin; exact no-op
    return m, x, v


def _star_planet_moon():
    ms, mp, mm = 1.0, 1e-3, 1e-6
    rp, rm = 1.0, 0.02
    vp = sqrt(G_(ms + mp) / rp)
    vm = sqrt(G_(mp + mm) / rm)
    x = [[0.0, 0.0, 0.0], [rp, 0.0, 0.0], [rp + rm, 0.0, 0.0]]
    v = [[0.0, 0.0, 0.0], [0.0, vp, 0.0], [0.0, vp + vm, 0.0]]
    x, v = _com_frame([ms, mp, mm], x, v)
    return [ms, mp, mm], x, v


def G_(mu):
    return 1.0 * mu


def _planet_of_two_stars():
    m1 = m2 = 0.5
    mp = 1e-4
    a = 0.2
    vrel = sqrt(G_(m1 + m2) / a)
    rp = 1.0
    vp = sqrt(G_(m1 + m2 + mp) / rp)
    x = [[-0.5 * a, 0.0, 0.0], [0.5 * a, 0.0, 0.0], [rp, 0.0, 0.0]]
    v = [[0.0, -0.5 * vrel, 0.0], [0.0, 0.5 * vrel, 0.0], [0.0, vp, 0.0]]
    x, v = _com_frame([m1, m2, mp], x, v)
    return [m1, m2, mp], x, v


def _random_masses():
    u = _uniform_stream(0xC0FFEE5EED)
    m = [0.5 + 1.5 * next(u) for _ in range(3)]
    x = [[2.0 * next(u) - 1.0, 2.0 * next(u) - 1.0, 0.0] for _ in range(3)]
    v = [[0.6 * next(u) - 0.3, 0.6 * next(u) - 0.3, 0.0] for _ in range(3)]
    x, v = _com_frame(m, x, v)
    return m, x, v


def _sd_scn(vx, vy):
    return lambda: _sd(vx, vy)


# key, name, aliases, builder, eta, period (None if not periodic), t_default, note
SCENARIOS = [
    ("1", "figure-8", ["figure8", "fig8", "eight", "moore", "chenciner-montgomery"],
     _figure8, 0.005, 6.32591398, 6.32591398, "Moore / Chenciner-Montgomery choreography"),
    ("2", "butterfly-i", ["butterfly", "butterfly1"], _sd_scn(0.30689, 0.12551), 0.01, 6.2356, 6.2356,
     "Suvakov-Dmitrasinovic family; 5-digit ICs (quasi-periodic)"),
    ("3", "moth-i", ["moth", "moth1"], _sd_scn(0.46444, 0.39606), 0.01, 14.8939, 14.8939,
     "Suvakov-Dmitrasinovic family; 5-digit ICs"),
    ("4", "yin-yang-i", ["yinyang", "yin-yang", "yinyang1", "yin-yang-ia"], _sd_scn(0.51394, 0.30474),
     0.01, 17.3284, 17.3284, "Suvakov-Dmitrasinovic Yin-Yang Ia; 5-digit ICs"),
    ("5", "yarn", [], _sd_scn(0.55906, 0.34919), 0.01, 55.5018, 20.0,
     "Suvakov-Dmitrasinovic family; 5-digit ICs"),
    ("6", "lagrange-chaos", ["lagrange", "lagrange-triangle", "triangle"], _lagrange, 0.01, None, 20.0,
     "Equilateral rotating triangle + fixed small kick -> chaos"),
    ("7", "burrau", ["burrau-3-4-5", "pythagorean", "345"], _burrau, 0.01, None, 20.0,
     "Pythagorean 3-4-5 problem, masses 3,4,5 at rest"),
    ("8", "star-planet-moon", ["starplanetmoon", "moon", "hierarchical"], _star_planet_moon,
     0.02, None, 20.0, "M=1, m=1e-3 at r=1, moon 1e-6 at 0.02 from planet"),
    ("9", "planet-of-two-stars", ["circumbinary", "p-type", "twostars"], _planet_of_two_stars,
     0.02, None, 20.0, "Equal binary a=0.2, planet 1e-4 at r=1"),
    ("0", "chaos-random", ["chaos", "random", "three-random-masses"], _random_masses,
     0.01, None, 20.0, "Three random masses, fixed splitmix64 seed"),
]


def _norm(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


def lookup(sel):
    """Resolve '1'..'9','0' or a (loosely matched) name to a scenario record, or None."""
    if sel is None:
        return None
    sel = str(sel).strip()
    for rec in SCENARIOS:
        if sel == rec[0]:
            return rec
    n = _norm(sel)
    if not n:
        return None
    for rec in SCENARIOS:
        if n == _norm(rec[1]) or n in [_norm(a) for a in rec[2]]:
            return rec
    return None


def build(sel):
    rec = lookup(sel)
    if rec is None:
        raise KeyError("unknown scenario: %r" % (sel,))
    m, x, v = rec[3]()
    return {
        "key": rec[0], "name": rec[1], "eta": rec[4], "period": rec[5],
        "t_default": rec[6], "note": rec[7],
        "m": [float(q) for q in m],
        "x": [[float(c) for c in p] for p in x],
        "v": [[float(c) for c in p] for p in v],
    }
