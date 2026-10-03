# metafield_nbody — gravitational N-body Field for MetaField / field-os

Deterministic, schema-compliant Newtonian N-body simulation with Forest-Ruth 4 symplectic integration, FieldTick provenance, golden-pinned operators, and a local 3D Celestial Field Observatory with an Interactive Dynamics Laboratory.

## Install & run

```bash
pip install -e .
python -m metafield_nbody --list
python -m metafield_nbody --scenario figure-8 --ticks 300
python -m metafield_nbody viz --scenario figure-8
```

## Celestial Field Observatory

```bash
python -m metafield_nbody viz [--scenario figure-8] [--port 8765]
```

Opens a local browser UI driven by the live `NBodyField` (authoritative). Features:

* 3D scene (Three.js): bodies, ephemeral + permanent trails, trail vectors, velocity/acceleration arrows
* Live telemetry matching Python state
* Mathematical inspector (equations, Forest-Ruth notes, softening)
* FieldTick provenance inspector
* Conservation plots from recorded history
* Scenario select / reset / export JSONL

## Interactive Dynamics Laboratory

Isolated fixed-step numerical experiments for integrator comparison, energy-drift
analysis, and parameter sweeps. Lab runs do **not** mutate the live `NBodyField`
or emit FieldTicks. The golden-pinned Forest-Ruth operator remains the Field baseline.

### Python API

```python
from metafield_nbody import experiment as E
from metafield_nbody import lab as Lab
from metafield_nbody.integrators import list_integrators

ic = E.bodies_from_scenario("figure-8")          # template (copy)
cfg = E.build_config(ic=ic, integrator_id="rk4", dt=1e-3, n_steps=1000)
result = Lab.run_experiment(cfg)
print(result["energy_analysis"]["rel_drift"])

# Derive a variant without mutating the parent
child = E.derive_config(cfg, {"dt": 5e-4}, label="half-dt")
r2 = Lab.run_experiment(child)
print(E.diff_configs(cfg, child))
```

### Integrators (lab only)

| id | order | symplectic | notes |
|---|---|---|---|
| `forest_ruth4_fixed` | 4 | yes | Same composition as Field operator; fixed dt |
| `velocity_verlet` | 2 | yes | Stormer-Verlet |
| `rk4` | 4 | no | Classical RK4; secular energy drift |
| `semi_implicit_euler` | 1 | yes | Euler-Cromer |
| `explicit_euler` | 1 | no | Pedagogic only |

### Observatory UI

Open the **Lab** tab:

1. Choose scenario template + integrator + dt + steps → **Run**.
2. Inspect energy drift plot and metrics (E0, relative drift, max/mean |dE|).
3. **Sweep dt** runs a background job over `{1e-3, 2e-3, 5e-3}`.
4. **Compare last two** shows pairwise config differences and drift summary.

HTTP API: `/api/lab/run`, `/api/lab/derive`, `/api/lab/compare`,
`/api/lab/sweep`, `/api/lab/experiments`, `/api/lab/integrators`.

### Reproducibility

Each experiment stores a versioned manifest (`manifest_version`, `config_digest`,
`run_digest`, parent lineage, software provenance). Identical configs on the same
platform yield identical `run_digest` values for lab integrators.

### Numerical limitations

* Lab integrators use fixed step size; adaptive control remains Field-only.
* Energy conservation is not a complete measure of trajectory accuracy.
* Trajectory separation tools are **numerical comparisons**, not verified Lyapunov exponents.
* Resource limits: max 32 bodies, 5e5 steps, duration <= 1000, <= 64 sweep samples.
* Invalid IC (non-positive mass, near-coincident bodies, non-finite values) are rejected — never silently repaired.

### Tests

```
python -m unittest tests.test_lab -v
python -m unittest discover -s tests
```

## Contract

`schemas/*.json` are v0.1 schemas shaped from the field-os README
(Observation → FieldDelta → FieldTick, provenance, synthetic ≠ physical).
All wire names live in `contract.py`. Reconcile with the real ones with:

```
python -m metafield_nbody.checker --schema-dir ../field-os/schema
```

## Formal checks

`python -m metafield_nbody.checker` (or `python -m unittest discover -s tests`):

* **Operator lock** — `operators.lock.json` pins operator version + source hash.
* **Goldens** — bit-exact recompute of 300 ticks per scenario.
* **Duck checker** — independent integrator audits logs.
* **Behavioural laws B1–B11** and figure-8 numerical laws N0–N4.

## Known limits (measured, not hidden)

* Figure-8 return error is bounded by the 8-digit published ICs (~1.6e-8).
* Adaptive dt is not strictly symplectic.
* Bitwise determinism relies on IEEE-754 `+ - * / sqrt` only in the primary operator.
* Pure Python: ~10^4 ticks/s-scale; not for long runs.
