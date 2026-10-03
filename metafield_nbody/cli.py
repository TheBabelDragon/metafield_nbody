"""Run scenarios.  Interactive keys (stdin) or scripted:
   python -m metafield_nbody --scenario figure-8 --until 2.1 --log out.jsonl
   python -m metafield_nbody --script "1 s s p s r q"
Keys: 1-9,0 select | s | s:N  step 1 / N ticks | p toggle pause | r reset | i invariants | q quit
"""
import argparse
import sys

from . import scenarios as S
from .field import NBodyField


def _status(f):
    inv = f.invariants()
    return ("%s t=%.9g tick=%d E=%.12e drift=%.2e |P|=%.2e Lz=%.6e%s"
            % (f.name, f.t, f.tick_no, inv["energy"], inv["energy_drift"],
               max(abs(c) for c in inv["momentum"]), inv["angular_momentum"][2],
               " [paused]" if f.paused else ""))


def _exec(f, toks):
    i = 0
    while i < len(toks) and not f.quit:
        t = toks[i]
        if t == "s" or t.startswith("s:"):
            ok, msg = f.command("step", int(t[2:]) if t.startswith("s:") else 1)
        elif t == "p":
            ok, msg = f.command("toggle")
        elif t == "r":
            ok, msg = f.command("reset")
        elif t == "q":
            ok, msg = f.command("quit")
        elif t == "i":
            ok, msg = True, _status(f)
        else:
            ok, msg = f.select(t)
        print(("ok  " if ok else "ERR ") + msg)
        if ok and t not in ("q",):
            print("    " + _status(f))
        i += 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Subcommand: viz → Celestial Field Observatory
    if argv and argv[0] == "viz":
        from .viz import main as viz_main
        return viz_main(argv[1:])

    ap = argparse.ArgumentParser(prog="metafield_nbody", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default="1", help="1-9,0 or name")
    ap.add_argument("--until", type=float, help="run to this simulation time")
    ap.add_argument("--ticks", type=int, help="run this many ticks")
    ap.add_argument("--log", help="write FieldTick JSONL")
    ap.add_argument("--script", help="space-separated key script")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    if a.list:
        for rec in S.SCENARIOS:
            print("%s  %-20s %s" % (rec[0], rec[1], rec[7]))
        return 0
    f = NBodyField(a.scenario)
    if a.script:
        _exec(f, a.script.split())
    elif a.until is not None or a.ticks is not None:
        f.run_until(a.until) if a.until is not None else f.advance(a.ticks)
        print(_status(f))
    else:                                        # interactive
        print(__doc__); print(_status(f))
        for line in sys.stdin:
            _exec(f, line.split())
            if f.quit:
                break
    if a.log:
        f.export_log(a.log)
    return 0
