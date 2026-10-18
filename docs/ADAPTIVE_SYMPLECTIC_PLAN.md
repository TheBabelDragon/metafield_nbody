# Adaptive Symplectic N-Body Engine — Inspection & Design

**Repository:** TheBabelDragon/metafield_nbody  
**Branch:** main  
**Date:** 2026-10-18  
**Status:** Foundational implementation on main; FieldTick path still 3-D.

## 1. Live inspection (baseline commit a137bd7)

### State representation
- Bodies: lists `m`, `x`, `v` where each position/velocity is a length-3 Python list.
- Spatial dimensionality was **hard-coded to 3** (now parameterised; default 3).

### Gravitational force law
- Softened Newtonian (Plummer), G=1.
- Now generalised: force magnitude ∝ 1/r^(D−1) for D ∈ {2,3,4}.

### Integration
- **Primary (FieldTick path):** Forest-Ruth 4 + adaptive dt — **unchanged**, still golden-pinned OPERATOR_VERSION 1.0.0.
- **Lab path:** fixed-step methods + **logh_leapfrog** (extended phase space).

### Configuration
- Lab manifests v1.1.0 include `dim`, force tag, integrator selection.

### C# / .NET
- Contract documented in `docs/ENGINE_BOUNDARY.md`. No runtime C# yet.

## 2. Selected adaptive symplectic method

**Primary references**

1. Preto, M. & Tremaine, S. 1999, *Astron. J.* 118, 2532 (arXiv:astro-ph/9906322)
2. Mikkola, S. & Tanikawa, K. 1999, *Celest. Mech. Dyn. Astron.* 74, 287

Implemented as `metafield_nbody/logh.py` → lab id `logh_leapfrog`.

### Guarantees stated accurately

- Symplectic in the **extended** phase space for fixed fictitious step Δτ.
- Physical timestep adapts via the time transformation.
- Exact Kepler property holds for pure inverse-square two-body (softening and N>2 limit this).
- Energy drift is diagnostic evidence, not a proof of symplecticity.

## 3. Completed on main (this effort)

| Item | Commit(s) |
|------|-----------|
| Design plan | 1216155 |
| Dim-parameterised physics operators | c079234 |
| Dim-aware lab integrators + dim tests | db1883e |
| LogH leapfrog module | 8519365 |
| LogH registry + unit tests | a69fdaf |
| README update | 4120425 |
| Experiment config `dim` (manifest 1.1.0) | b5464f6 |
| Lab runner dim plumbing | 2d4f375 |
| C# engine boundary doc | a111201 |
| Stronger LogH tests, IC helpers, benchmarks | a27e377 |

## 4. Remaining milestones

1. Higher-order LogH compositions (Yoshida) optional.
2. Optional dim on FieldTick path (requires OPERATOR_VERSION bump + golden regen).
3. Formal benchmark table checked into docs.
4. C# prototype only after Python reference suite is green and stable.

## 5. Known limitations (honest)

- Softening breaks the pure Kepler exactness of LogH.
- Multi-body close encounters are not chain-regularised.
- FieldTick emission and stock scenarios remain 3-D.
- Adaptive Forest-Ruth on the Field path is still **not** claimed strictly symplectic.
- Pure Python performance is reference-scale only.

---

*All claims of symplecticity are grounded in the published derivation and the concrete update map, not in observed energy drift alone.*
