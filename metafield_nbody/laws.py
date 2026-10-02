"""Formal laws.  Each law returns (id, ok, detail).  Behavioural (B*) and
numerical (N*) laws; run by checker.py and tests."""
import itertools
import math

from . import contract as C
from . import scenarios as S
from .field import NBodyField, replay, S_KEYS
from . import duck


def _r(i, ok, d=""):
    return (i, bool(ok), d)


def behavioural():
    out = []
    # B1 select by key and by name
    ok = True; det = ""
    for rec in S.SCENARIOS:
        for sel in (rec[0], rec[1], rec[1].upper(), rec[1].replace("-", " ")):
            f = NBodyField("1")
            good, _ = f.select(sel)
            if not good or f.name != rec[1] or f.key != rec[0]:
                ok = False; det = "select %r -> %r" % (sel, f.name)
    out.append(_r("B1 select by 1-0 key or by (loose) name", ok, det))
    # B2 invalid select rejected, state untouched
    f = NBodyField("2"); f.advance(5)
    snap = (f.name, f.t, f.tick_no, f.digest, len(f.log))
    r1 = [f.select(s)[0] for s in ("99", "nope", "", None, "11")]
    r2 = f.command("frobnicate")[0]
    out.append(_r("B2 invalid select/command rejected, no state change, no delta",
                  not any(r1) and not r2 and snap == (f.name, f.t, f.tick_no, f.digest, len(f.log))))
    # B3 select resets and emits genesis tick 0
    f.select("3")
    out.append(_r("B3 select resets t=0, tick=0, emits one valid genesis tick",
                  f.t == 0.0 and f.tick_no == 0 and len(f.log) == 1 and f.name == "moth-i"
                  and not C.check_tick(f.log[0], C.genesis_digest("moth-i"), 0)))
    # B4 pause / resume
    f = NBodyField("1"); f.advance(3)
    f.command("pause"); n, t = len(f.log), f.t
    got = f.advance(10) + f.run_until(1.0)
    paused_ok = (not got) and len(f.log) == n and f.t == t
    f.command("resume"); got2 = f.advance(2)
    out.append(_r("B4 pause freezes time/emission; resume continues", paused_ok and len(got2) == 2))
    f.command("toggle"); a = f.paused; f.command("toggle")
    out.append(_r("B4b toggle flips pause state", a and not f.paused))
    # B5 quit
    f = NBodyField("1"); f.advance(2)
    ok1 = f.command("quit")[0]
    n, t = len(f.log), f.t
    ok2 = (not f.advance(5)) and (not f.select("2")[0]) and (not f.command("resume")[0])
    out.append(_r("B5 quit is terminal: no steps, no select, no emission",
                  ok1 and ok2 and len(f.log) == n and f.t == t and f.quit))
    # B6 determinism of the digest chain (stable + chaotic)
    ok = True
    for key in ("1", "6", "0"):
        a = NBodyField(key); a.advance(120)
        b = NBodyField(key); b.advance(120)
        ok &= [x["digest"] for x in a.log] == [x["digest"] for x in b.log]
    out.append(_r("B6 bit-identical digest chain across independent runs", ok))
    # B7 replay
    f = NBodyField("8"); f.advance(80)
    rp = replay(f.log)
    live = [{"m": f.m[i], "x": f.x[i], "v": f.v[i]} for i in range(len(f.m))]
    tam = [dict(t) for t in f.log]; tam[40] = dict(tam[40]); tam[40]["t"] += 1e-9
    try:
        replay(tam); rej = False
    except C.ContractViolation:
        rej = True
    out.append(_r("B7 replay from deltas == live state bitwise; tampered log refused",
                  rp["bodies"] == live and rp["digest"] == f.digest and rej))
    # B8 synthetic vs physical
    f = NBodyField("1")
    try:
        f.ingest_observation({"kind": "Observation", "origin": "physical"}); ok = False
    except C.ContractViolation:
        ok = True
    out.append(_r("B8 physical observations refused (synthetic != physical)", ok))
    # B9 admission of every emitted tick, consecutive indices, ordering
    f = NBodyField("9"); f.advance(60)
    out.append(_r("B9 every emitted tick passes schema+semantic admission", not C.check_log(f.log)))
    # B10 reset reproduces genesis
    f = NBodyField("4"); g0 = f.digest; f.advance(30); f.command("reset")
    out.append(_r("B10 reset reproduces identical genesis digest", f.digest == g0 and f.tick_no == 0))
    # B11 independent audit of a log from every scenario
    ok = True
    for rec in S.SCENARIOS:
        f = NBodyField(rec[0]); f.advance(40)
        ok &= not duck.full_verify_log(f.log)
    out.append(_r("B11 independent audit passes on all 10 scenarios", ok))
    return out


def figure8():
    out = []
    f = NBodyField("1")
    x0 = [list(p) for p in f.x]; v0 = [list(p) for p in f.v]
    T3 = f.period / 3.0
    drift = 0.0; pmax = 0.0; ldrift = 0.0
    e0, l0 = f.inv0["energy"], f.inv0["angular_momentum"]
    while f.t < T3:
        tk = f._one_tick(t_limit=T3)
        if tk is None:
            break
        inv = f.invariants()
        drift = max(drift, inv["energy_drift"])
        pmax = max(pmax, max(abs(c) for c in inv["momentum"]))
        ldrift = max(ldrift, max(abs(inv["angular_momentum"][k] - l0[k]) for k in range(3)))
    best = None
    for perm in itertools.permutations(range(3)):
        ex = max(abs(f.x[i][k] - x0[perm[i]][k]) for i in range(3) for k in range(3))
        ev = max(abs(f.v[i][k] - v0[perm[i]][k]) for i in range(3) for k in range(3))
        e = max(ex, ev)
        if best is None or e < best[0]:
            best = (e, perm)
    err, perm = best
    is_3cycle = all(perm[i] != i for i in range(3))
    out.append(_r("N0 run lands exactly on t = T/3 (bitwise)", f.t == T3, repr(f.t)))
    out.append(_r("N1 bodies return (3-cycle permuted) within 1e-7 after T/3",
                  err < 1e-7 and is_3cycle, "err=%.3e perm=%s" % (err, perm)))
    out.append(_r("N2 max relative energy drift < 1e-9", drift < 1e-9, "%.3e" % drift))
    out.append(_r("N3 linear momentum ~ 0 (max |P| < 1e-12)", pmax < 1e-12, "%.3e" % pmax))
    out.append(_r("N4 angular momentum drift < 1e-9", ldrift < 1e-9, "%.3e" % ldrift))
    return out


def all_laws():
    return behavioural() + figure8()
