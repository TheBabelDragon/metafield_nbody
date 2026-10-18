"""Logarithmic Hamiltonian (extended phase-space) adaptive symplectic integrator.

Primary references
------------------
* Preto, M. & Tremaine, S. 1999, Astron. J. 118, 2532
  "A class of symplectic integrators with adaptive timestep for separable
  Hamiltonian systems"  (arXiv:astro-ph/9906322)

* Mikkola, S. & Tanikawa, K. 1999, Celest. Mech. Dyn. Astron. 74, 287
  "Explicit symplectic algorithms for time-transformed Hamiltonians"

Mathematical outline
--------------------
Original Hamiltonian H = T(p) + U(q).
Introduce fictitious time τ with dt = g dτ and extend phase space by the
conjugate pair (t, p₀ = −H).  The logarithmic choice

    Γ = log(T + B) − log(−U)     (U < 0 for bound systems)

yields a separable extended Hamiltonian.  A fixed step Δτ in fictitious time
then produces an adaptive physical timestep while the map remains symplectic
in the extended phase space.

For a pure inverse-square two-body problem the leapfrog form integrates the
Kepler ellipse exactly (only a phase / time error remains).

Implementation notes
--------------------
* Softening is retained for consistency with the rest of the engine; the exact
  Kepler property holds only in the unsoftened inverse-square limit.
* B (binding energy shift) defaults to −E₀ (initial total energy).  A small
  positive floor prevents log-of-zero when kinetic energy vanishes.
* The method is exposed as a *lab* integrator.  The golden-pinned Forest-Ruth
  operator used for FieldTick emission is not altered by this module.
* Strict symplecticity is claimed only for the extended-space map with fixed
  Δτ; physical-time adaptivity is a consequence of the time transformation.
"""
from __future__ import annotations

from math import sqrt, log, exp, inf
from typing import List, Optional, Tuple

from . import physics as P

Vec = List[float]


def _kinetic(m, v, dim):
    ke = 0.0
    for i in range(len(m)):
        s = 0.0
        for c in range(dim):
            s += v[i][c] * v[i][c]
        ke += 0.5 * m[i] * s
    return ke


def _potential(m, x, dim):
    """Softened potential energy (negative for bound systems)."""
    n = len(m)
    pe = 0.0
    for i in range(n - 1):
        for j in range(i + 1, n):
            r2 = P.EPS2
            for c in range(dim):
                d = x[j][c] - x[i][c]
                r2 += d * d
            pe -= P.G * m[i] * m[j] * P._pair_potential(r2, dim)
    return pe


def _accelerations(m, x, dim):
    return P.accelerations(m, x, dim=dim)


def logh_leapfrog_step(
    m,
    x,
    v,
    dtau,
    *,
    dim=3,
    B=None,
    t=0.0,
    eps_floor=1e-30,
):
    """One second-order LogH leapfrog step in fictitious time.

    Parameters
    ----------
    m, x, v : body masses, positions, velocities
    dtau : fixed fictitious-time step
    dim : spatial dimensionality
    B : binding-energy shift (default = −E if E < 0, else 1.0)
    t : current physical time (advanced and returned)
    eps_floor : numerical floor inside logarithms

    Returns
    -------
    x_new, v_new, t_new, info

    info contains diagnostic fields: dtau, dt_physical, T, U, B, converged.
    """
    dim = int(dim)
    n = len(m)
    x = [list(p) for p in x]
    v = [list(q) for q in v]

    T = _kinetic(m, v, dim)
    U = _potential(m, x, dim)

    if B is None:
        E = T + U
        B = -E if E < 0.0 else 1.0
    B = float(B)

    # --- drift half-step (coordinates advance; momenta fixed) ---------------
    # d q / dτ = ∂Γ/∂p = (1/(T+B)) * ∂T/∂p = v / (T+B)
    # d t / dτ = 1/(T+B)
    denom_T = max(T + B, eps_floor)
    h_half = 0.5 * dtau / denom_T
    for i in range(n):
        for c in range(dim):
            x[i][c] += h_half * v[i][c]
    t = t + h_half

    # --- kick (momenta advance; coordinates fixed) --------------------------
    # d p / dτ = -∂Γ/∂q = (1/(-U)) * (-∂U/∂q) = a / (-U)   for U < 0
    # With softening U is still negative for bound systems.
    U = _potential(m, x, dim)
    denom_U = max(-U, eps_floor)
    a = _accelerations(m, x, dim)
    kick = dtau / denom_U
    for i in range(n):
        for c in range(dim):
            v[i][c] += kick * a[i][c]

    # --- drift half-step again ----------------------------------------------
    T = _kinetic(m, v, dim)
    denom_T = max(T + B, eps_floor)
    h_half = 0.5 * dtau / denom_T
    for i in range(n):
        for c in range(dim):
            x[i][c] += h_half * v[i][c]
    t = t + h_half

    dt_physical = dtau * (0.5 / max(_kinetic(m, v, dim) + B, eps_floor)
                          + 0.5 / max(T + B, eps_floor))  # rough diagnostic

    info = {
        "dtau": dtau,
        "dt_physical_est": h_half * 2.0,  # last full drift contribution proxy
        "T": T,
        "U": U,
        "B": B,
        "converged": True,
        "dim": dim,
    }
    return x, v, t, info


def logh_leapfrog(m, x, v, h, G=None, soft2=None, dim=3, B=None):
    """Lab-compatible wrapper: interpret ``h`` as fictitious step Δτ.

    Signature matches other lab integrators (m, x, v, h, ...) so it can be
    registered in INTEGRATORS.  Physical time is not returned through this
    interface; use logh_leapfrog_step for full diagnostics.
    """
    # G / soft2 overrides are not yet wired; the module uses physics defaults.
    x_new, v_new, _t, _info = logh_leapfrog_step(
        m, x, v, h, dim=dim, B=B
    )
    return x_new, v_new
