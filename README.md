# metafield_nbody — gravitational N-body Field for MetaField / field-os

Deterministic, schema-compliant Newtonian N-body simulation with Forest-Ruth 4
symplectic integration, FieldTick provenance, golden-pinned operators, a local
3D Celestial Field Observatory, and an Interactive Dynamics Laboratory.

**Recent (2026-10-18):** dimension-parameterised force operators (D = 2, 3, 4)
and a laboratory logarithmic-Hamiltonian (extended phase-space) integrator
following Preto & Tremaine / Mikkola & Tanikawa. See
[`docs/ADAPTIVE_SYMPLECTIC_PLAN.md`](docs/ADAPTIVE_SYMPLECTIC_PLAN.md).

## Install & run

Requires **Python 3.10+**. No third-party packages are required for the core
Field, CLI, lab, or doctor diagnostics. The observatory UI loads Three.js from a CDN.

### Externally managed environments (Arch Linux, Debian/Ubuntu, Fedora, …)

System Python is often marked *externally managed* (PEP 668). Do **not** run
`pip install` against the system interpreter. Use a virtual environment:

**Arch Linux**

```bash
# optional if missing: sudo pacman -S python python-virtualenv
git clone https://github.com/TheBabelDragon/metafield_nbody
cd metafield_nbody
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e .
```

**Debian / Ubuntu**

```bash
sudo apt install python3 python3-venv python3-pip   # once
git clone https://github.com/TheBabelDragon/metafield_nbody
cd metafield_nbody
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

**Any platform (same pattern)**

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
```

If `python -m venv` fails with `ensurepip is not available`, install the distro
venv package (`python-virtualenv` on Arch, `python3-venv` on Debian/Ubuntu) and
retry. Avoid `--break-system-packages` unless you accept the risk.

### Run without installing (optional)

From the repo root, with the package directory on `PYTHONPATH`:

```bash
cd metafield_nbody   # repo root
PYTHONPATH=. python -m metafield_nbody doctor
PYTHONPATH=. python -m metafield_nbody viz --scenario figure-8
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
* **Dimensional operators**: `physics.accelerations` / `invariants` / `forest_ruth4_step`
  accept `dim` (default 3). When `dim=3` the floating-point sequence is identical
  to the golden-pinned OPERATOR_VERSION 1.0.0 path.

### What is not claimed

* Visualization FPS is not a physics timestep.
* Energy conservation monitoring is **not** a complete proof of trajectory accuracy.
* Trajectory separation tools are **numerical comparisons**, not Lyapunov proofs.
* Adaptive-dt Forest-Ruth is not strictly symplectic; close encounters increase drift.
* Exact cross-platform bitwise identity is not promised beyond IEEE-754 assumptions.
* The LogH lab integrator is symplectic in the *extended* phase space; physical-time
  adaptivity is a consequence of the time transformation, not an independent claim.

## Dimensional generalisation (D = 2, 3, 4)

Force law follows the D-dimensional Gauss-law convention:

| D | Force magnitude | Notes |
|---|-----------------|-------|
| 2 | ∝ 1/r           | logarithmic potential |
| 3 | ∝ 1/r²          | classic Newtonian (default) |
| 4 | ∝ 1/r³          | extra coordinate `w` participates fully |

Angular momentum is the full set of independent components of the antisymmetric
tensor (1 component in 2-D, 3 in 3-D, 6 in 4-D).

Scenarios and the FieldTick path remain 3-D for now; lab integrators and pure
operators accept `dim`.

## Logarithmic Hamiltonian integrator (lab)

```python
from metafield_nbody.integrators import get_step
step = get_step("logh_leapfrog")
x2, v2 = step(m, x, v, dtau, dim=3)   # dtau = fixed fictitious step
```

Or with full diagnostics:

```python
from metafield_nbody import logh as LH
x2, v2, t2, info = LH.logh_leapfrog_step(m, x, v, dtau, dim=3, B=B, t=t)
```

References: Preto & Tremaine (1999), Mikkola & Tanikawa (1999).
Design notes and limitations: `docs/ADAPTIVE_SYMPLECTIC_PLAN.md`.

## Verification

```bash
python3 -m venv .venv && source .venv/bin/activate   # see Install if needed
pip install -e .
python -m metafield_nbody doctor
python -m unittest discover -s tests -v
python -m metafield_nbody --scenario figure-8 --ticks 100
python -m metafield_nbody viz --scenario figure-8 --no-browser
```

Integrity tests (`tests/test_integrity.py`) independently recompute K, U, E, P, L;
verify Field→snapshot correspondence; verify export/replay; reject corrupted logs.

New tests: `tests/test_dimensions.py`, `tests/test_logh.py`.

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
`semi_implicit_euler`, `explicit_euler`, **`logh_leapfrog`**.

## Contract & formal checks

Operator lock, goldens, duck checker, behavioural laws B1–B11, figure-8 numerical
laws. See `python -m metafield_nbody.checker`.

## Known limits (measured, not hidden)

* Figure-8 return error is bounded by the 8-digit published ICs (~1.6e-8).
* Adaptive dt (Forest-Ruth Field path) is not strictly symplectic.
* LogH is symplectic in extended phase space; softening and multi-body encounters
  limit the exact Kepler property to the idealised two-body inverse-square case.
* Pure Python: ~10^4 ticks/s-scale; not for long production runs.
* Scenario library and FieldTick emission remain 3-D; higher-D is available at the
  operator / lab layer.
