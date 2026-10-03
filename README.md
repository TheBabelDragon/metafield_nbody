# metafield_nbody — gravitational N-body Field for MetaField / field-os

Deterministic, schema-compliant Newtonian N-body simulation with Forest-Ruth 4
symplectic integration, FieldTick provenance, golden-pinned operators, a local
3D Celestial Field Observatory, and an Interactive Dynamics Laboratory.

## Install & run

```bash
pip install -e .
python -m metafield_nbody doctor
python -m metafield_nbody --list
python -m metafield_nbody --scenario figure-8 --ticks 300
python -m metafield_nbody viz --scenario figure-8
```

## Scientific Integrity

Authoritative simulation state lives in `NBodyField`. The visualization and lab
layers **display** or **copy** that state; they do not invent positions, energies,
or FieldTicks.

```
Physics (physics.py)
  ↓
NBodyField  ──emit──► FieldTick (hashed, schema-validated)
  ↓                      ↓
VizSession            export JSONL
  ↓                      ↓
HTTP /api/state       load_log → replay
  ↓
Browser (Three.js) — render coordinates = payload coordinates
```

### What is guaranteed

* **Deterministic Field runs** on a given platform: same scenario + same advance
  count → bit-identical state and digest chain (IEEE-754 `+ - * / sqrt` only in
  the primary operator).
* **FieldTick chain integrity**: digests hash-chain; tampering fails `check_log` / `replay`.
* **Transport fidelity**: `/api/state` body positions/velocities/time/tick/digest
  match the live `NBodyField` (no unit conversion, no axis swap).
* **Softened Newtonian model**: potential energy uses the same Plummer softening
  (`ε²`) as the force law (G = 1 normalized units).
* **Lab experiments**: fixed-step integrators with versioned manifests
  (`config_digest`, `run_digest`, parent lineage). Isolated from FieldTick emission.

### What is not claimed

* Visualization FPS is not a physics timestep.
* Energy conservation monitoring is **not** a complete proof of trajectory accuracy.
* Trajectory separation tools are **numerical comparisons**, not Lyapunov proofs.
* Adaptive-dt Forest-Ruth is not strictly symplectic; close encounters increase drift.
* Exact cross-platform bitwise identity is not promised beyond IEEE-754 assumptions.

## Verification

```bash
pip install -e .
python -m metafield_nbody doctor
python -m unittest discover -s tests -v
python -m metafield_nbody --scenario figure-8 --ticks 100
python -m metafield_nbody viz --scenario figure-8 --no-browser
```

Integrity tests (`tests/test_integrity.py`) independently recompute K, U, E, P, L;
verify Field→snapshot correspondence; verify export/replay; reject corrupted logs.

## Celestial Field Observatory

```bash
python -m metafield_nbody viz [--scenario figure-8] [--port 8765]
```

3D scene driven by the live `NBodyField` (authoritative): trails, vectors,
telemetry, mathematical inspector, FieldTick provenance, conservation plots.

## Interactive Dynamics Laboratory

Isolated fixed-step experiments (integrator comparison, energy-drift analysis,
parameter sweeps). Lab runs do **not** mutate the live Field or emit FieldTicks.

```python
from metafield_nbody import experiment as E, lab as Lab
ic = E.bodies_from_scenario("figure-8")
cfg = E.build_config(ic=ic, integrator_id="rk4", dt=1e-3, n_steps=1000)
result = Lab.run_experiment(cfg)
print(result["energy_analysis"]["rel_drift"])
```

Lab integrators: `forest_ruth4_fixed`, `velocity_verlet`, `rk4`,
`semi_implicit_euler`, `explicit_euler`.

## Contract & formal checks

Operator lock, goldens, duck checker, behavioural laws B1–B11, figure-8 numerical
laws. See `python -m metafield_nbody.checker`.

## Known limits (measured, not hidden)

* Figure-8 return error is bounded by the 8-digit published ICs (~1.6e-8).
* Adaptive dt is not strictly symplectic.
* Pure Python: ~10^4 ticks/s-scale; not for long production runs.
