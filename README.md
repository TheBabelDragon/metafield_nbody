# metafield_nbody — gravitational N-body Field for MetaField / field-os

Deterministic, schema-compliant Newtonian N-body simulation with Forest-Ruth 4
symplectic integration, FieldTick provenance, golden-pinned operators, a local
3D Celestial Field Observatory, and an Interactive Dynamics Laboratory.

**Recent (2026-10-18):** dimension-parameterised force operators (D = 2, 3, 4)
and laboratory logarithmic-Hamiltonian integrators (2nd-order leapfrog +
Yoshida 4th-order) following Preto & Tremaine / Mikkola & Tanikawa. See
[`docs/ADAPTIVE_SYMPLECTIC_PLAN.md`](docs/ADAPTIVE_SYMPLECTIC_PLAN.md) and
[`docs/ENGINE_BOUNDARY.md`](docs/ENGINE_BOUNDARY.md).

## Install & run

Requires **Python 3.10+**. No third-party packages are required for the core
Field, CLI, lab, or doctor diagnostics. The observatory UI loads Three.js from a CDN.

### Externally managed environments (Arch Linux, Debian/Ubuntu, Fedora, …)

System Python is often marked *externally managed* (PEP 668). Do **not** run
`pip install` against the system interpreter. Use a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
```

### Run

```bash
python -m metafield_nbody doctor
python -m metafield_nbody --list
python -m metafield_nbody --scenario figure-8 --ticks 300
python -m metafield_nbody viz --scenario figure-8
```

## Scientific Integrity

Authoritative simulation state lives in `NBodyField`. The visualization and lab
layers **display** or **copy** that state; they do not invent positions, energies,
or FieldTicks.

### What is guaranteed

* **Deterministic Field runs** on a given platform: same scenario + same advance
  count → bit-identical state and digest chain (IEEE-754 `+ - * / sqrt` only in
  the primary operator).
* **FieldTick chain integrity**: digests hash-chain; tampering fails `check_log` / `replay`.
* **Softened Newtonian model**: potential energy uses the same Plummer softening
  (`ε²`) as the force law (G = 1 normalized units).
* **Dimensional operators**: `physics.accelerations` / `invariants` / `forest_ruth4_step`
  accept `dim` (default 3). When `dim=3` the floating-point sequence is identical
  to the golden-pinned OPERATOR_VERSION 1.0.0 path.

### What is not claimed

* Adaptive-dt Forest-Ruth is not strictly symplectic.
* LogH is symplectic in the *extended* phase space; physical-time adaptivity is
  a consequence of the time transformation.
* Energy conservation alone does not prove trajectory accuracy.

## Dimensional generalisation (D = 2, 3, 4)

| D | Force magnitude |
|---|-----------------|
| 2 | ∝ 1/r           |
| 3 | ∝ 1/r²          |
| 4 | ∝ 1/r³          |

Scenarios and the FieldTick path remain 3-D; lab integrators accept `dim`.

## Logarithmic Hamiltonian integrators (lab)

```python
from metafield_nbody.integrators import get_step
step = get_step("logh_yoshida4")   # or "logh_leapfrog"
x2, v2 = step(m, x, v, dtau, dim=3)
```

References: Preto & Tremaine (1999), Mikkola & Tanikawa (1999), Yoshida (1990).

## Verification

```bash
pip install -e .
python -m metafield_nbody doctor
python -m unittest discover -s tests -v
PYTHONPATH=. python benchmarks/bench_step.py
```

## Interactive Dynamics Laboratory

```python
from metafield_nbody import experiment as E, lab as Lab
ic = E.bodies_from_scenario("figure-8")
cfg = E.build_config(ic=ic, integrator_id="logh_yoshida4", dt=1e-2, n_steps=500)
result = Lab.run_experiment(cfg)
print(result["energy_analysis"]["rel_drift"])
```

Lab integrators: `forest_ruth4_fixed`, `velocity_verlet`, `rk4`,
`semi_implicit_euler`, `explicit_euler`, `logh_leapfrog`, `logh_yoshida4`.

## Known limits

* Figure-8 return error bounded by 8-digit published ICs (~1.6e-8).
* Adaptive Forest-Ruth (Field path) is not strictly symplectic.
* LogH exact Kepler property holds only for pure inverse-square two-body.
* Pure Python: reference-scale performance only.
* Stock scenarios / FieldTick emission remain 3-D.
