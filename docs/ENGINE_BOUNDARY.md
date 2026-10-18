# MetaField N-Body Engine Boundary (C# / .NET readiness)

**Status:** Design contract only. Python remains the sole implementation.
**Date:** 2026-10-18
**Version:** 0.1.0-draft

## Purpose

Define a clean, versioned boundary between:

1. Simulation configuration
2. Body / phase-space state
3. Force models
4. Integrators
5. Runtime diagnostics & checkpoints
6. Serialisation
7. Visualisation / projection

so that a future standalone .NET/C# numerical core can implement the same
contract and be validated against the existing Python reference cases
without requiring a cross-language bridge in the interim.

## Design principles

* **Pure data in / pure data out.** No hidden global state inside the
  numerical core.
* **Dimensionality is a first-class parameter** (`Dim` ∈ {2, 3, 4, …}).
* **Force model and integrator are selectable strategies**, not hard-wired.
* **Symplecticity claims are attached to the concrete update map**, not to
  observed energy drift.
* **Visual / camera parameters never enter the physics boundary.**

## Suggested C# surface (illustrative)

```csharp
// Namespace: MetaField.NBody.Engine

public readonly record struct BodyState(
    double Mass,
    ReadOnlyMemory<double> Position,   // length = Dim
    ReadOnlyMemory<double> Velocity    // length = Dim
);

public sealed class SimulationConfig
{
    public int Dim { get; init; } = 3;                 // 2, 3, or 4
    public string IntegratorId { get; init; } = "forest_ruth4_fixed";
    public string ForceModelId { get; init; } = "softened_newtonian";
    public double G { get; init; } = 1.0;
    public double Softening { get; init; } = 1e-6;
    public double Dt { get; init; }                    // physical or fictitious
    public int? NSteps { get; init; }
    public double? Duration { get; init; }
    public int? Seed { get; init; }
    public Dictionary<string, double> IntegratorParams { get; init; } = new();
    // e.g. { "eta": 0.01, "dt_min": 1e-7, "B": ... } for adaptive methods
}

public interface IForceModel
{
    string Id { get; }
    int Dim { get; }
    // a[i][c] += ...
    void Accelerations(
        ReadOnlySpan<double> masses,
        ReadOnlySpan<double> positions,  // n * dim
        Span<double> accelerations);
    double PotentialEnergy(
        ReadOnlySpan<double> masses,
        ReadOnlySpan<double> positions);
}

public interface IIntegrator
{
    string Id { get; }
    int Order { get; }
    bool ClaimsSymplecticity { get; }  // of the concrete map
    string Notes { get; }

    // Advance state by one step. May interpret dt as physical or fictitious.
    IntegratorStepResult Step(
        ReadOnlySpan<double> masses,
        Span<double> positions,
        Span<double> velocities,
        double dt,
        IForceModel force,
        in IntegratorContext ctx);
}

public readonly record struct IntegratorContext(
    int Dim,
    double? BindingEnergyShift,   // LogH B parameter
    double PhysicalTime,
    int MaxIterations,
    double Tolerance
);

public readonly record struct IntegratorStepResult(
    bool Converged,
    double PhysicalTimeAdvanced,
    int IterationsUsed,
    string? Diagnostic
);

public readonly record struct Invariants(
    double Kinetic,
    double Potential,
    double Energy,
    double[] Momentum,           // length Dim
    double[] AngularMomentum,    // length Dim*(dim-1)/2
    double Mass,
    double[] CentreOfMass        // length Dim
);

public interface IDiagnostics
{
    Invariants Compute(
        ReadOnlySpan<double> masses,
        ReadOnlySpan<double> positions,
        ReadOnlySpan<double> velocities,
        IForceModel force);
}

// Checkpoint / serialisation — JSON schema compatible with Python manifests
public interface ICheckpointStore
{
    void Save(string path, SimulationConfig config, BodyState[] bodies,
              double time, Invariants inv, string? runDigest);
    (SimulationConfig, BodyState[], double, Invariants) Load(string path);
}
```

## Mapping from current Python modules

| Concern            | Python today                         | Future C#                             |
|--------------------|--------------------------------------|---------------------------------------|
| Config             | `experiment.build_config`            | `SimulationConfig`                    |
| State              | lists `m, x, v`                      | `BodyState[]` / flat spans            |
| Force              | `physics.accelerations`              | `IForceModel`                         |
| Integrators        | `integrators.py`, `logh.py`          | `IIntegrator` implementations         |
| Invariants         | `physics.invariants`                 | `IDiagnostics`                        |
| FieldTick path     | `field.py` + `contract.py`           | optional higher-level host            |
| Lab experiments    | `lab.run_experiment`                 | host that drives `IIntegrator`        |
| Visualisation      | `viz.py` / Three.js                  | outside the numerical core            |

## Validation requirement

Any C# implementation that claims interchangeability **must** pass the same
reference cases used by the Python suite:

* Two-body circular / elliptical orbits (energy + period diagnostics)
* Figure-8 choreography return error (when ICs match)
* Dimensional force-law scaling tests (D = 2, 3, 4)
* LogH bound-orbit stability (when that integrator is implemented)
* Deterministic replay of a fixed config → identical digests on the same platform

Until those tests pass, the C# core is experimental and not a drop-in.

## Non-goals (this phase)

* No P/Invoke or gRPC bridge.
* No dual maintenance of two production engines.
* No claim that the Python adaptive Forest-Ruth path is strictly symplectic.

## Next steps when implementing C#

1. Port `physics.accelerations` / `_force_factor` / `invariants` first.
2. Port fixed-step Velocity Verlet and Forest-Ruth4.
3. Port LogH leapfrog with the same B-handling and floors.
4. Wire golden / reference vectors from `tests/`.
5. Only then consider FieldTick / provenance emission in C#.
