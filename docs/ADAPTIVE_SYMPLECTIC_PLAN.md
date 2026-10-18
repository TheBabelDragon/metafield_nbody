# Adaptive Symplectic N-Body Engine — Inspection & Design

**Repository:** TheBabelDragon/metafield_nbody  
**Branch:** main  
**Date:** 2026-10-18  
**Status:** Foundational design committed; implementation in progress.

## 1. Live inspection (commit a137bd7)

### State representation
- Bodies: lists `m`, `x`, `v` where each position/velocity is a length-3 Python list.
- Spatial dimensionality is **hard-coded to 3** in every force, leapfrog, invariant, and scenario builder.
- No abstract vector type; coordinate loops are written as `[0]`, `[1]`, `[2]` or `range(3)`.

### Gravitational force law
- Softened Newtonian (Plummer):
  ```
  r² = |x₊ − x₉|² + ε²
  f  = G / (r² * sqrt(r²))
  a₊ += f * m₉ * (x₉ − x₊)
  ```
- Equivalent to force magnitude ∝ 1/r³ (inverse-square force in 3-D).
- Potential consistent with the force: U = −G m₊ m₉ / sqrt(r² + ε²).
- G = 1, ε = 1e-6 (module constants).

### Integration
- **Primary (FieldTick path):** Forest-Ruth 4 composed of three leapfrogs with weights θ, 1−2θ, θ where θ = 1/(2−2^(1/3)).
- Adaptive physical timestep from free-fall / fly-by times (eta-controlled).
- README explicitly states: adaptive Forest-Ruth is **not** strictly symplectic.
- **Lab path:** fixed-step variants (Forest-Ruth4, Velocity Verlet, RK4, …) for comparison; do not emit FieldTicks.

### Configuration & persistence
- Scenarios hard-coded; eta, DT_MIN, DT_MAX module-level.
- FieldTick provenance includes operator name/version, src SHA of physics operators, params block.
- No general runtime config object for dimensionality or integrator choice.

### Language / C# boundary
- Pure Python, no C#/.NET components, no FFI.
- Clean operator boundary already exists (`physics.py` is pure functions).

### Tests
- Integrity (recompute invariants, digest chain, replay).
- Behavioural laws B1–B11.
- Figure-8 numerical laws N0–N4.
- Lab and viz tests.

## 2. Selected adaptive symplectic method

**Primary references**

1. Preto, M. & Tremaine, S. 1999, *Astron. J.* 118, 2532  
   “A class of symplectic integrators with adaptive timestep for separable Hamiltonian systems”  
   arXiv:astro-ph/9906322

2. Mikkola, S. & Tanikawa, K. 1999, *Celest. Mech. Dyn. Astron.* 74, 287  
   “Explicit symplectic algorithms for time-transformed Hamiltonians”

### Mathematical outline (to be implemented exactly)

- Original Hamiltonian H = T(p) + U(q).
- Introduce fictitious time τ via dt = g dτ.
- Extend phase space: new coordinate q₀ = t, conjugate momentum p₀ = −H.
- Extended Hamiltonian 
  ```
  Γ(Q, P) = g(q, p, t) * (H(q, p) + p₀)
  ```
  Trajectories of interest lie on the surface Γ = 0.

- For the logarithmic (algorithmic regularisation) choice used by Mikkola & Tanikawa / Preto & Tremaine:
  ```
  Γ = log(T + B) − log(U + C)     (or equivalent forms)
  ```
  where B is a binding-energy constant (often −H₀ or a fixed positive shift) and C is a small positive regulariser when needed.

- The resulting map is separable in the extended space and admits an **explicit** leapfrog (or higher-order composition) with **fixed** step Δτ. The physical timestep Δt therefore adapts automatically.

- For pure inverse-square two-body motion the method integrates the Kepler ellipse exactly (only a phase/time error remains).

### Implementation constraints (this work)

- Keep the golden-pinned Forest-Ruth4 operator in `physics.py` **unchanged** (OPERATOR_VERSION stays 1.0.0 until a deliberate bump + golden regeneration).
- New integrator lives in a separate module and is selectable.
- Explicit convergence criteria, iteration limits, and failure diagnostics for any implicit solve that appears.
- Never claim strict symplecticity solely from small energy drift; claim is based on the derivation of the update map.
- Existing adaptive Forest-Ruth remains the default FieldTick path until the new method has passed the full test suite and golden compatibility checks.

## 3. Spatial dimensionality generalisation

Target: D ∈ {2, 3, 4} at minimum.

### Force-law convention (documented choice)

Newtonian gravity generalised by the D-dimensional Gauss law:

- Force magnitude scales as 1 / r^(D−1)
- Potential scales as  
  - r^(2−D) / (D−2)   for D ≠ 2  
  - log(r)             for D = 2

With Plummer softening the practical forms used will be:

```
r2s = |x_i − x_j|² + ε²
r   = sqrt(r2s)

# force factor f such that a_i += f * m_j * (x_j − x_i)
if D == 3:
    f = G / (r2s * r)          # classic, recovers existing code
elif D == 2:
    f = G / r2s                # 1/r force
elif D == 4:
    f = G / (r2s * r2s)        # 1/r³ force
else:
    f = G / (r2s ** ((D-1)/2))
```

Potential is computed consistently with the chosen force so that energy diagnostics remain meaningful.

The additional coordinate for D=4 is named `w` and participates fully in the dynamics; visualisation projects (x,y,z) or any chosen 3-subset.

### State representation plan

- Introduce `DIM` (or per-run `dim`) as a validated configuration parameter.
- Positions and velocities become length-`dim` lists (or a thin Vector abstraction that still uses plain lists for bit-identical behaviour).
- All pure operators (`accelerations`, leapfrogs, invariants, adaptive_dt) become dimension-parameterised while preserving exact numerical results for dim=3.

## 4. Configuration surface (planned)

A validated `SimulationConfig` (or extension of existing params) will expose:

- `dim` ∈ {2,3,4}
- `integrator` ∈ {"forest_ruth4_adaptive", "logh_leapfrog", …}
- physical / adaptation parameters appropriate to each integrator
- G, softening, body count / IC generator, random seed
- solver tolerances, max iterations, diagnostic flags

Visual / camera parameters remain strictly separate.

## 5. C# engine boundary (non-disruptive)

Document a minimal, versioned contract that isolates:

- configuration
- body / phase-space state
- force models
- integrators
- diagnostics / checkpoints

No language rewrite in this phase. The pure-function style of `physics.py` already forms a natural boundary for a future .NET core.

## 6. Priority order (strict)

1. Mathematical correctness of the selected method
2. Working adaptive (extended-phase-space) integrator with diagnostics
3. Dimensional generalisation (D=2,3,4)
4. Configurable, reproducible experiments
5. C# contract documentation
6. Performance measurement

## 7. Known limitations (to be kept honest)

- The logarithmic Hamiltonian method is symplectic in the *extended* phase space; physical-time adaptive stepping inherits the usual caveats of time transformations.
- Softening changes the force law; exact Kepler property holds only for pure inverse-square (or the special quasi-Keplerian cases discussed in the literature).
- Close encounters with many bodies still require care; the method is not a full chain regularisation.
- Cross-platform bit-identity remains limited to IEEE-754 + / − * / sqrt assumptions already stated for Forest-Ruth.

## 8. Next concrete milestones

1. Add this document (done).
2. Dimension-parameterised accelerations + invariants that reproduce existing 3-D results exactly.
3. Minimal LogH leapfrog implementation behind a lab-selectable integrator, with unit tests against two-body Kepler and energy/phase diagnostics.
4. Config object + dim selection for scenarios.
5. Full test expansion and documentation of numerical guarantees.

---

*All claims of symplecticity will be grounded in the published derivation and the concrete update map, not in observed energy drift alone.*
