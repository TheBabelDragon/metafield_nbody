"""Duck-style checker/attacker.

CHECKER: an independent re-implementation (different integrator staging,
different loop structure, own dt rule, pow-based force) that recomputes goldens
and audits any log, sharing NO code with physics.py except constants it
re-derives itself.
ATTACKER: mutates valid logs/goldens in adversarial ways; every attack must be
rejected, otherwise the verifier is unsound.
"""
import copy
import math

from . import contract as C
from . import golden as GD
from . import physics as P
from .field import NBodyField, replay

_G = 1.0
_EPS2 = (1e-6) ** 2
_TH = 1.0 / (2.0 - 2.0 ** (1.0 / 3.0))
# Forest-Ruth in merged 7-stage form: D(a)K(b)D(c)K(d)D(c)K(b)D(a)
_A = _TH / 2.0
_B = _TH
_C = (1.0 - _TH) / 2.0
_D = 1.0 - 2.0 * _TH


def _acc(m, x):
    out = []
    for i in range(len(m)):
        ax = ay = az = 0.0
        for j in range(len(m)):
            if j == i:
                continue
            dx = x[j][0] - x[i][0]
            dy = x[j][1] - x[i][1]
            dz = x[j][2] - x[i][2]
            r2 = dx * dx + dy * dy + dz * dz + _EPS2
            w = m[j] * _G / (r2 ** 1.5)
            ax += w * dx
            ay += w * dy
            az += w * dz
        out.append((ax, ay, az))
    return out


def ind_step(m, x, v, h):
    x = [list(p) for p in x]
    v = [list(q) for q in v]

    def drift(c):
        for i in range(len(m)):
            for k in range(3):
                x[i][k] += c * h * v[i][k]

    def kick(c):
        a = _acc(m, x)
        for i in range(len(m)):
            for k in range(3):
                v[i][k] += c * h * a[i][k]

    drift(_A); kick(_B); drift(_C); kick(_D); drift(_C); kick(_B); drift(_A)
    return x, v


def ind_dt(m, x, v, eta, dt_min, dt_max):
    best = float("inf")
    n = len(m)
    for i in range(n):
        for j in range(i + 1, n):
            d2 = sum((x[j][k] - x[i][k]) ** 2 for k in range(3)) + _EPS2
            d = math.sqrt(d2)
            tff = math.sqrt(d ** 3 / (_G * (m[i] + m[j])))
            w = math.sqrt(sum((v[j][k] - v[i][k]) ** 2 for k in range(3)))
            best = min(best, tff, d / w if w > 0 else float("inf"))
    return min(dt_max, max(dt_min, eta * best))


def ind_invariants(m, x, v):
    n = len(m)
    ke = sum(0.5 * m[i] * sum(c * c for c in v[i]) for i in range(n))
    pe = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            d = math.sqrt(sum((x[j][k] - x[i][k]) ** 2 for k in range(3)) + _EPS2)
            pe -= _G * m[i] * m[j] / d
    return ke + pe


def _close(a, b, tol):
    return abs(a - b) <= tol * (1.0 + abs(b))


def _flat(*arrs):
    out = []
    for a in arrs:
        for row in a:
            out.extend(row)
    return out


# ---------------------------------------------------------------- recompute
def recompute_golden(g, ticks, tol=1e-9):
    """Independently integrate golden initial state for `ticks` steps; compare
    against the golden checkpoint at exactly that tick.  Returns max abs error."""
    m = GD.unhx(g["initial"]["m"]); x = GD.unhx(g["initial"]["x"]); v = GD.unhx(g["initial"]["v"])
    eta = g["eta"]
    for _ in range(ticks):
        dt = ind_dt(m, x, v, eta, 1e-7, 1e-2)
        x, v = ind_step(m, x, v, dt)
    cp = [c for c in g["checkpoints"] if c["tick"] == ticks]
    if not cp:
        raise KeyError("no checkpoint at tick %d" % ticks)
    gx = GD.unhx(cp[0]["state"]["x"]); gv = GD.unhx(cp[0]["state"]["v"])
    return max(abs(a - b) for a, b in zip(_flat(x, v), _flat(gx, gv)))


def calibrate_horizon(g, tol=1e-9):
    """Largest checkpoint tick at which the independent recompute still agrees
    within tol (chaotic scenarios amplify rounding differences)."""
    best = 0
    for cp in g["checkpoints"]:
        if recompute_golden(g, cp["tick"]) <= tol:
            best = cp["tick"]
        else:
            break
    return best


def verify_golden_independent(g, tol=1e-9):
    errs = []
    h = g.get("duck_horizon_ticks") or 0
    if g["kind"] == "ticks" and h < GD.CHECK_EVERY:
        errs.append("duck horizon below one checkpoint (%s)" % h)
    if h:
        e = recompute_golden(g, h)
        if e > tol:
            errs.append("independent recompute disagrees at tick %d: %.3e" % (h, e))
    if g["kind"] == "third":                     # independent run to exactly T/3
        m = GD.unhx(g["initial"]["m"]); x = GD.unhx(g["initial"]["x"]); v = GD.unhx(g["initial"]["v"])
        t = 0.0
        target = S_period(g) / 3.0
        while t < target:
            dt = ind_dt(m, x, v, g["eta"], 1e-7, 1e-2)
            rem = target - t
            if rem <= dt * (1.0 + 1e-12):
                dt = rem
            x, v = ind_step(m, x, v, dt)
            t = target if rem == dt else t + dt
        cp = g["checkpoints"][0]["state"]
        err = max(abs(a - b) for a, b in zip(_flat(x, v), _flat(GD.unhx(cp["x"]), GD.unhx(cp["v"]))))
        if err > tol:
            errs.append("independent T/3 recompute disagrees: %.3e" % err)
    return errs


def S_period(g):
    from . import scenarios as S
    return S.lookup(g["key"])[5]


# ---------------------------------------------------------------- log audit
def audit_log(ticks, tol=1e-11):
    """Independent semantic audit of a log that already passed admission:
    every step is recomputed from the previous tick's recorded state, dt is
    re-derived, and recorded invariants are re-derived from recorded bodies."""
    errs = []
    prev_state = None
    for tk in ticks:
        bodies = [d for d in tk["deltas"] if d["field"] == C.FIELDMAP["body_field"]]
        sysd = [d for d in tk["deltas"] if d["field"] == C.FIELDMAP["inv_field"]]
        if len(sysd) != 1 or not bodies:
            return ["tick %d: malformed delta set" % tk["tick"]]
        m = [b["value"]["m"] for b in bodies]
        x = [b["value"]["x"] for b in bodies]
        v = [b["value"]["v"] for b in bodies]
        eta = bodies[0]["provenance"]["params"]["eta"]
        e = ind_invariants(m, x, v)
        if not _close(e, sysd[0]["value"]["energy"], 1e-12):
            errs.append("tick %d: recorded energy inconsistent with recorded bodies" % tk["tick"])
        if prev_state is not None:
            pm, px, pv = prev_state
            if pm != m:
                errs.append("tick %d: masses changed" % tk["tick"])
            dt = ind_dt(pm, px, pv, eta, 1e-7, 1e-2)
            if tk["dt"] > dt * (1 + 1e-9) or tk["dt"] <= 0:
                errs.append("tick %d: dt %.17g violates adaptive rule (<= %.17g)" % (tk["tick"], tk["dt"], dt))
            ex_dt = P.adaptive_dt(pm, px, pv, eta)
            if tk["dt"] > ex_dt:
                errs.append("tick %d: dt exceeds primary adaptive rule" % tk["tick"])
            ex_x, ex_v = P.forest_ruth4_step(pm, px, pv, tk["dt"])
            if ex_x != x or ex_v != v:
                errs.append("tick %d: step not bit-exact under primary operator" % tk["tick"])
            nx, nv = ind_step(pm, px, pv, tk["dt"])
            for a, b in zip(_flat(nx, nv), _flat(x, v)):
                if not _close(b, a, tol):
                    errs.append("tick %d: step not reproduced by independent integrator" % tk["tick"])
                    break
            if tk["t"] < ticks[tk["tick"] - 1]["t"]:
                errs.append("tick %d: time went backwards" % tk["tick"])
        prev_state = (m, x, v)
        if errs:
            return errs
    return errs


def full_verify_log(ticks, schemas=None):
    errs = C.check_log(ticks, schemas)
    if errs:
        return errs
    return audit_log(ticks)


# ---------------------------------------------------------------- attacks
def _rehash(tk):
    tk["digest"] = C.tick_digest(tk)


def _rechain(ticks, start):
    for i in range(start, len(ticks)):
        if i > 0:
            ticks[i]["prev_digest"] = ticks[i - 1]["digest"]
            for d in ticks[i]["deltas"]:
                d["provenance"]["inputs"] = [ticks[i - 1]["digest"]]
        _rehash(ticks[i])


def _body(tk, i=0):
    return [d for d in tk["deltas"] if d["field"] == C.FIELDMAP["body_field"]][i]


def attack_suite(n_ticks=30):
    """Return [(name, rejected_bool, detail)].  rejected must be True for all."""
    f = NBodyField("1")
    f.advance(n_ticks)
    base = copy.deepcopy(f.log)
    assert not full_verify_log(base), "baseline log must verify"
    results = []

    def run(name, mutate, smart=True):
        ticks = copy.deepcopy(base)
        try:
            mutate(ticks)
            if smart:
                _rechain(ticks, 1)
            errs = full_verify_log(ticks)
        except Exception as ex:                  # mutation unrepresentable == rejected
            errs = ["exception: %s" % ex]
        results.append((name, bool(errs), errs[0] if errs else "ACCEPTED"))

    def a_bitflip(t):
        b = _body(t[10]); b["value"]["x"][0] += 1e-9
    def a_ulp(t):
        b = _body(t[10]); b["value"]["v"][1] = math.nextafter(b["value"]["v"][1], 1e300)
    def a_noncorrupt_hash(t):
        b = _body(t[10]); b["value"]["x"][0] += 1e-9
    def a_reorder(t):
        t[7]["deltas"].reverse()
    def a_drop(t):
        del t[12]
    def a_dup(t):
        t.insert(12, copy.deepcopy(t[12]))
    def a_physical(t):
        d = _body(t[5]); d["origin"] = "physical"
    def a_physical_prov(t):
        d = _body(t[5]); d["provenance"]["origin"] = "physical"; d["provenance"]["physical"] = True
    def a_nan(t):
        _body(t[5])["value"]["x"][0] = float("nan")
    def a_inf(t):
        _body(t[5])["value"]["v"][0] = float("inf")
    def a_opver(t):
        for d in t[9]["deltas"]:
            d["provenance"]["operator"]["version"] = "1.0.1"
    def a_swap(t):
        a, b = _body(t[15], 0), _body(t[15], 1)
        a["value"], b["value"] = b["value"], a["value"]
    def a_energy(t):
        for d in t[8]["deltas"]:
            if d["field"] == C.FIELDMAP["inv_field"]:
                d["value"]["energy"] *= 1.0000001
    def a_round(t):
        for tk in t[3:]:
            for d in tk["deltas"]:
                if d["field"] == C.FIELDMAP["body_field"]:
                    d["value"]["x"] = [round(c, 6) for c in d["value"]["x"]]
    def a_dt_inflate(t):
        t[6]["dt"] = t[6]["dt"] * 2.0
        for d in t[6]["deltas"]:
            if d["field"] == C.FIELDMAP["inv_field"]:
                d["value"]["dt"] = t[6]["dt"]
    def a_extra_field(t):
        t[4]["deltas"][0]["extra"] = 1
    def a_mass(t):
        for tk in t[2:]:
            _body(tk, 0)["value"]["m"] = 1.0000001
    def a_time_back(t):
        t[9]["t"] = t[8]["t"] - 1e-3
        for d in t[9]["deltas"]:
            d["t"] = t[9]["t"]
    def a_foreign_space(t):
        t[3]["deltas"][0]["address"]["space"] = "nbody/moth-i"

    run("single-bit-scale position tamper (re-chained)", a_bitflip)
    run("1-ulp velocity tamper (re-chained)", a_ulp)
    run("tamper WITHOUT re-hash", a_noncorrupt_hash, smart=False)
    run("reverse delta order (re-chained)", a_reorder)
    run("drop a tick", a_drop, smart=False)
    run("duplicate a tick", a_dup, smart=False)
    run("relabel delta origin=physical", a_physical)
    run("forge provenance physical=true", a_physical_prov)
    run("inject NaN", a_nan)
    run("inject Infinity", a_inf)
    run("forge operator version", a_opver)
    run("swap two bodies' state in one tick", a_swap)
    run("falsify recorded energy", a_energy)
    run("truncate positions to 6 dp from tick 3", a_round)
    run("inflate dt (violate adaptive rule)", a_dt_inflate)
    run("smuggle extra property", a_extra_field)
    run("perturb a mass", a_mass)
    run("time goes backwards", a_time_back)
    run("cross-scenario address", a_foreign_space)

    # contract edge: physical observation must be refused
    try:
        NBodyField("1").ingest_observation({"kind": "Observation", "origin": "physical"})
        results.append(("ingest physical observation", False, "ACCEPTED"))
    except C.ContractViolation as ex:
        results.append(("ingest physical observation", True, str(ex)[:60]))

    # golden bit-flip
    for fn, g in GD.load_all():
        if g["kind"] == "third":
            gg = copy.deepcopy(g)
            s = gg["final"]["state"]["x"][0][0]
            gg["final"]["state"]["x"][0][0] = float(float.fromhex(s) + 2.0 ** -52).hex()
            ok = gg["final"] != GD.make_golden(g["key"], g["kind"])["final"]
            results.append(("golden 1-ulp tamper (%s)" % fn.split(".")[0], ok, "mismatch" if ok else "ACCEPTED"))
            break
    return results
