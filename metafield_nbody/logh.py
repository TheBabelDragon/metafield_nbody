"""Logarithmic Hamiltonian (extended phase-space) adaptive symplectic integrator.

Primary references
------------------
* Preto, M. & Tremaine, S. 1999, Astron. J. 118, 2532
  "A class of symplectic integrators with adaptive timestep for separable
  Hamiltonian systems"  (arXiv:astro-ph/9906322)

* Mikkola, S. & Tanikawa, K. 1999, Celest. Mech. Dyn. Astron. 74, 287
  "Explicit symplectic algorithms for time-transformed Hamiltonians"

* Yoshida, H. 1990, Phys. Lett. A 150, 262 — composition for 4th-order

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

The 4th-order method composes three 2nd-order LogH leapfrogs with Yoshida
weights (θ, 1−2θ, θ) where θ = 1/(2−2^(1/3)), identical to the Forest-Ruth
coefficient already used in physics.py.

Implementation notes
--------------------
* Softening is retained for consistency with the rest of the engine; the exact
  Kepler property holds only in the unsoftened inverse-square limit.
* B (binding energy shift) defaults to −E₀ (initial total energy).  A small
  positive floor prevents log-of-zero when kinetic energy vanishes.
* Methods are exposed as *lab* integrators.  The golden-pinned Forest-Ruth
  operator used for FieldTick emission is not altered by this module.
* Strict symplecticity is claimed only for the extended-space map with fixed
  Δτ; physical-time adaptivity is a consequence of the time transformation.
"""
from __future__ import annotations

from math import sqrt
from typing import List

from . import physics as P

Vec = List[float]

# Yoshida / Forest-Ruth weight (same constant as physics.THETA)
_YOSHIDA_THETA = P.THETA
_YOSHIDA_W0 = P.W0


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

    Returns
    -------
    x_new, v_new, t_new, info
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

    # drift half
    denom_T = max(T + B, eps_floor)
    h_half = 0.5 * dtau / denom_T
    for i in range(n):
        for c in range(dim):
            x[i][c] += h_half * v[i][c]
    t = t + h_half

    # kick
    U = _potential(m, x, dim)
    denom_U = max(-U, eps_floor)
    a = _accelerations(m, x, dim)
    kick = dtau / denom_U
    for i in range(n):
        for c in range(dim):
            v[i][c] += kick * a[i][c]

    # drift half
    T = _kinetic(m, v, dim)
    denom_T = max(T + B, eps_floor)
    h_half = 0.5 * dtau / denom_T
    for i in range(n):
        for c in range(dim):
            x[i][c] += h_half * v[i][c]
    t = t + h_half

    info = {
        "dtau": dtau,
        "dt_physical_est": h_half * 2.0,
        "T": T,
        "U": U,
        "B": B,
        "converged": True,
        "dim": dim,
        "order": 2,
    }
    return x, v, t, info


def logh_yoshida4_step(
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
    """Fourth-order LogH step via Yoshida composition of three leapfrogs.

    φ₄(Δτ) = φ₂(θ Δτ) ∘ φ₂((1−2θ) Δτ) ∘ φ₂(θ Δτ)
    with θ = 1/(2−2^(1/3)).
    """
    dim = int(dim)
    x = [list(p) for p in x]
    v = [list(q) for q in v]

    if B is None:
        T = _kinetic(m, v, dim)
        U = _potential(m, x, dim)
        E = T + U
        B = -E if E < 0.0 else 1.0
    B = float(B)

    x, v, t, _ = logh_leapfrog_step(
        m, x, v, _YOSHIDA_THETA * dtau, dim=dim, B=B, t=t, eps_floor=eps_floor
    )
    x, v, t, _ = logh_leapfrog_step(
        m, x, v, _YOSHIDA_W0 * dtau, dim=dim, B=B, t=t, eps_floor=eps_floor
    )
    x, v, t, info = logh_leapfrog_step(
        m, x, v, _YOSHIDA_THETA * dtau, dim=dim, B=B, t=t, eps_floor=eps_floor
    )
    info = dict(info)
    info["dtau"] = dtau
    info["order"] = 4
    info["composition"] = "yoshida"
    return x, v, t, info


def logh_leapfrog(m, x, v, h, G=None, soft2=None, dim=3, B=None):
    """Lab-compatible wrapper: h = fixed fictitious step Δτ (2nd order)."""
    x_new, v_new, _t, _info = logh_leapfrog_step(
        m, x, v, h, dim=dim, B=B
    )
    return x_new, v_new


def logh_yoshida4(m, x, v, h, G=None, soft2=None, dim=3, B=None):
    """Lab-compatible wrapper: h = fixed fictitious step Δτ (4th order)."""
    x_new, v_new, _t, _info = logh_yoshida4_step(
        m, x, v, h, dim=dim, B=B
    )
    return x_new, v_new
