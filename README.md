# metafield_nbody — gravitational N-body Field for MetaField / field-os

Newtonian gravity (G=1, softening 1e-6), 4th-order symplectic Forest-Ruth
(three leapfrogs, theta = 1/(2-2^(1/3))), adaptive step
`dt = eta * min_pairs(min(free-fall, fly-by))`, 3D vectors, N bodies.
Stdlib only, Python >= 3.8. Drop the package + `.babel/` into the
metafield-engine tree (or run in place).

## Celestial Field Observatory (visualization)

Interactive 3D scientific visualization of the live `NBodyField`. The Python
simulation remains the single source of truth; the browser is a presentation
and instrumentation layer.

```
python -m metafield_nbody viz
python -m metafield_nbody viz --scenario figure-8
python -m metafield_nbody viz --scenario burrau --port 8765
python -m metafield_nbody viz --no-browser
```

Opens `http://127.0.0.1:8765/` (stdlib HTTP server, no extra dependencies).
Three.js is loaded from CDN in the browser.

### Architecture

```
NBodyField  →  VizSession (history + control)  →  HTTP/JSON API
                                                      ↓
                                              Browser (Three.js)
                                         3D scene · telemetry · math · Field
```

- **3D scene** — mass-scaled luminous bodies, orbital trails, velocity /
  acceleration vectors, COM marker, grid, axes, orbit/pan/zoom, bloom,
  cinematic mode.
- **Mathematics inspector** — equations of motion as implemented (softened
  Newtonian force), Forest-Ruth update structure, parameters (G, ε, η, θ,
  dt bounds), known numerical limits.
- **Invariants** — energy, kinetic, potential, relative drift, linear & angular
  momentum, centre of mass; live values + history plots.
- **Field inspector** — digest chain, prev_digest, tick payload viewer,
  operator provenance, contract admission status, JSONL export.
- **Scenario laboratory** — all ten built-in scenarios; select / reset /
  frame camera.

Visual body sizes and vector lengths are display-only and do not affect
physics. Interpolated display frames are never fed back into the integrator.

### Controls

| UI | Action |
|---|---|
| ▶ / ⏸ | Play / pause |
| ⏭ | Single step |
| ↺ | Reset to genesis |
| Scenario menu | Load any scenario (resets run) |
| Speed slider | Target ticks per wall-second |
| Scene panel | Toggle trails, vectors, labels, grid, COM, axes, bloom, cinematic |
| Body click | Select body → mass / x / v / a + pairwise table |

### Mathematical model (as implemented)

```
dr_i / dt = v_i
dv_i / dt = G Σ_{j≠i} m_j (r_j − r_i) / (|r_j − r_i|² + ε²)^{3/2}

E = Σ ½ m_i |v_i|² − Σ_{i<j} G m_i m_j / √(|r_i − r_j|² + ε²)
P = Σ m_i v_i
L = Σ m_i (r_i × v_i)
```

G = 1, Plummer softening ε = 1e-6. Integrator: Forest-Ruth 4th-order
(three leapfrogs). Adaptive `dt = η · min(free-fall, fly-by)` — **not**
strictly symplectic; close encounters increase energy drift (see Known limits).

This visualization is a MetaField Field *consumer and inspector*, not a
standalone orbital toy: every displayed tick was admitted by the contract
layer and hash-chained.

### Tests

```
python -m unittest tests.test_viz -v
python -m unittest discover -s tests
```

## Run (CLI)

```
python -m metafield_nbody --list
python -m metafield_nbody --scenario figure-8 --until 2.1086 --log fig8.jsonl
python -m metafield_nbody --script "1 s:100 p s r 6 s:50 i q"     # scripted
python -m metafield_nbody                                         # interactive on stdin
```
Keys: `1-9,0` select (0 = scenario 10) or a name · `s`/`s:N` step · `p` pause toggle ·
`r` reset · `i` invariants · `q` quit.

```python
from metafield_nbody import NBodyField, replay
f = NBodyField("yin yang"); f.run_until(1.0)
f.invariants()          # energy, momentum, angular_momentum, energy_drift
replay(f.log)           # admits the whole log, rebuilds state from deltas only
```

| key | name | notes |
|---|---|---|
| 1 | figure-8 | Chenciner-Montgomery, period 6.32591398 |
| 2 | butterfly-i | Suvakov-Dmitrasinovic |
| 3 | moth-i | " |
| 4 | yin-yang-i | Ia |
| 5 | yarn | " |
| 6 | lagrange-chaos | equilateral rotating triangle + fixed small kick |
| 7 | burrau | 3-4-5, masses 3,4,5 at rest |
| 8 | star-planet-moon | 1 / 1e-3 / 1e-6 |
| 9 | planet-of-two-stars | circumbinary planet |
| 0 | chaos-random | 3 random masses, fixed splitmix64 seed |

## Contract

One tick = one integration step (genesis tick 0 = full initial state). Each tick
holds one `gravity.body_state` FieldDelta per body + one `gravity.invariants`
FieldDelta, **sorted by (space, cell, field)**, hash-chained
(`digest = sha256(canonical_json(tick minus digest))`, `prev_digest` links).
Every delta carries full provenance (operator name/version/source hash, params,
predecessor digest, `origin: synthetic`, `physical: false`). The field refuses
physical observations. Emission is gated: a tick that fails admission raises
instead of being emitted.

### IMPORTANT — schema status
`.babel/schemas/*.json` are v0.1 schemas shaped from the field-os README
(Observation → FieldDelta → FieldTick, provenance, synthetic ≠ physical).
All wire names live in `contract.py` (`FIELDMAP`, `build_delta`, `build_tick`,
`provenance`). Reconcile with the real ones with:

```
python -m metafield_nbody.checker --schema-dir ../field-os/schema
```

## Formal checks

`python -m metafield_nbody.checker` (or `python -m unittest discover -s tests`):

* **Operator lock** — `operators.lock.json` pins operator version + source hash and the SHA-256 of every golden. Changing physics requires bumping `OPERATOR_VERSION` and `checker --regen`.
* **Goldens** (`tests/golden/`, 11 files, all floats as `float.hex`) — bit-exact recompute of 300 ticks per scenario, plus the figure-8 run to exactly T/3.
* **Duck checker** — independent integrator (merged 7-stage FR, own dt rule, pow-based force) recomputes goldens and audits any log step-by-step; also an exact replay with the primary operator.
* **Duck attacker** — 21 attacks (tamper with/without re-hash, 1-ulp edits, reorder, drop/duplicate tick, forged origin/provenance/operator version, NaN/Inf, energy falsification, truncation, dt inflation, extra properties, time reversal, cross-scenario address, physical-observation ingestion, golden bit-flip). All must be rejected.
* **Behavioural laws B1–B11**: select by key/name, invalid input refused with no state change, select resets + genesis, pause/resume, quit terminal, deterministic chains, replay == live state, synthetic/physical separation, admission, reset, audit on all 10 scenarios.
* **Figure-8 numerical laws N0–N4** (measured): lands on t = T/3 bitwise; 3-cycle return error 1.6e-8 (< 1e-7); energy drift 2.4e-11 (< 1e-9); |P| 4.7e-15; angular-momentum drift 3.8e-15.

## Known limits (measured, not hidden)

* Figure-8 return error is bounded by the 8-digit published ICs (~1.6e-8), not the integrator.
* Adaptive dt is not strictly symplectic. Close-encounter scenarios drift more over 20 time units: burrau 1.8e-7, chaos-random 2.8e-7, butterfly/yin-yang ~1e-8. Only figure-8 carries the 1e-9 guarantee.
* Suvakov-Dmitrasinovic ICs (2,3,4,5) are 5-digit values, so those orbits are approximate. Yarn's period is listed but only the first 20 time units are default.
* Bitwise determinism relies on IEEE-754 `+ - * / sqrt` only (no trig/pow in the primary operator). The independent checker uses `**` and is tolerance-based by design.
* Pure Python: ~10^4 ticks/s-scale; not for long runs.
