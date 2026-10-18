#!/usr/bin/env python3
"""Micro-benchmark: integration step cost vs body count and dimensionality.

Usage (from repo root):

    PYTHONPATH=. python benchmarks/bench_step.py

Reports mean wall time per step for forest_ruth4_fixed and logh_leapfrog.
Not a formal performance claim — pure-Python reference numbers only.
"""
from __future__ import annotations

import time
from math import sqrt

from metafield_nbody.integrators import get_step
from metafield_nbody import physics as P


def make_cluster(n, dim=3, seed=1):
    # simple deterministic lattice-like placement
    m = [1.0] * n
    x, v = [], []
    k = 0
    side = int(sqrt(n)) + 1
    for i in range(n):
        coords = [0.0] * dim
        coords[0] = (i % side) * 0.8 - 0.4 * side
        coords[1] = ((i // side) % side) * 0.8 - 0.4 * side
        if dim >= 3:
            coords[2] = (i // (side * side)) * 0.8
        if dim >= 4:
            coords[3] = 0.1 * (i % 3)
        x.append(coords)
        vel = [0.0] * dim
        vel[0] = 0.01 * ((i % 5) - 2)
        vel[1] = 0.01 * ((i % 7) - 3)
        v.append(vel)
    return m, x, v


def bench(integrator_id, n_bodies, dim, n_steps=200, warmup=20):
    m, x, v = make_cluster(n_bodies, dim=dim)
    step = get_step(integrator_id)
    # warmup
    xx, vv = [list(p) for p in x], [list(q) for q in v]
    for _ in range(warmup):
        xx, vv = step(m, xx, vv, 1e-3, dim=dim)
    xx, vv = [list(p) for p in x], [list(q) for q in v]
    t0 = time.perf_counter()
    for _ in range(n_steps):
        xx, vv = step(m, xx, vv, 1e-3, dim=dim)
    elapsed = time.perf_counter() - t0
    return elapsed / n_steps


def main():
    print("integrator            N   dim   us/step")
    print("-" * 42)
    for integ in ("forest_ruth4_fixed", "logh_leapfrog", "velocity_verlet"):
        for n in (2, 8, 16):
            for dim in (2, 3, 4):
                try:
                    dt = bench(integ, n, dim)
                    print("%s  %3d  %3d  %8.1f" % (integ.ljust(20), n, dim, dt * 1e6))
                except Exception as exc:
                    print("%s  %3d  %3d  FAIL: %s" % (integ.ljust(20), n, dim, exc))


if __name__ == "__main__":
    main()
