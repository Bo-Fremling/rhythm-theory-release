"""Σ / RP holonomy utilities for FLAVOR_LOCK.

Intent
- In Core, PP is primary and continuous; measurement happens on the RP screen Σ via C30 strob.
- Certain global constraints (notably the Global Frame closure L_* = 1260 = 30·42 and the derived cap L_cap)
  induce a deterministic flavor-space transport.

Representation policy
- We allow *two equivalent* realizations of the same transport, both deterministic and knob-free:
  (A) Σ / RP readout holonomy:     U <- H · U    (left multiplication on the screen), and
  (B) PP-generator embedding:      Ue <- Ue · H†  (right multiplication inside the charged-lepton generator),
      so that PMNS = Ue†Uν becomes PMNS = (Ue·H†)†Uν = H·(Ue†Uν).

This module provides a minimal, explicit representation of that holonomy as left-multiplication on
mixing matrices (CKM/PMNS) without interpreting it as an arbitrary basis rotation.

Rules
- No SI. No scans. Deterministic only.
- Discrete angles only (derived from C30 and sextet engagement).
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore


def theta_sextet_unit() -> float:
    """Base discrete angle: 2π/(30·6) = 2°."""
    return float(2.0 * math.pi / (30.0 * 6.0))


def cap_magnitude(L_bias: int = 6, L_arm: int = 1) -> int:
    """Deterministic cap magnitude: |L_cap| = (bias-nollning) + (P-ARM)."""
    return int(L_bias) + int(L_arm)


def cap_length(L_bias: int = 6, L_arm: int = 1, removed_endcap: bool = True) -> int:
    """Deterministic signed cap length.

    Sign convention:
    - removed_endcap=True  => L_cap = -|L_cap| (transport correction for a removed tail segment)
    - removed_endcap=False => L_cap = +|L_cap| (NEG control)
    """
    mag = cap_magnitude(L_bias=L_bias, L_arm=L_arm)
    return -mag if bool(removed_endcap) else +mag


def holonomy_rotation(axis: str, theta: float):
    """Return a real rotation matrix in the requested flavor plane.

    axis:
      - '12' rotates (1,2)
      - '13' rotates (1,3)
      - '23' rotates (2,3)

    Returned matrix is complex dtype to match other construct code.
    """
    if np is None:
        raise RuntimeError("numpy required")

    axis = str(axis)
    c = float(math.cos(theta))
    s = float(math.sin(theta))

    if axis == "12":
        R = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    elif axis == "13":
        R = np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]], dtype=np.complex128)
    elif axis == "23":
        R = np.array([[1.0, 0.0, 0.0], [0.0, c, s], [0.0, -s, c]], dtype=np.complex128)
    else:
        raise ValueError(f"unknown axis '{axis}'")
    return R


def cap_holonomy(axis: str = "23", L_bias: int = 6, L_arm: int = 1, removed_endcap: bool = True) -> Tuple["np.ndarray", Dict[str, float]]:
    """Σ-holonomy induced by the Global Frame cap.

    Returns (H, meta) where H multiplies a readout matrix U on the LEFT: U <- H · U.

    For PMNS, axis='23' rotates μ/τ rows and leaves the e-row unchanged.
    """
    if np is None:
        raise RuntimeError("numpy required")

    th_unit = theta_sextet_unit()
    L_cap = cap_length(L_bias=L_bias, L_arm=L_arm, removed_endcap=removed_endcap)
    theta = float(th_unit * float(L_cap))
    H = holonomy_rotation(axis=str(axis), theta=theta)

    meta: Dict[str, float] = {
        "theta_unit_rad": float(th_unit),
        "theta_unit_deg": float(math.degrees(th_unit)),
        "L_bias": float(L_bias),
        "L_arm": float(L_arm),
        "L_cap": float(L_cap),
        "theta_cap_rad": float(theta),
        "theta_cap_deg": float(math.degrees(theta)),
        "removed_endcap": float(1.0 if removed_endcap else 0.0),
    }
    return H, meta


def apply_holonomy(U, H):
    """Apply Σ-holonomy: U <- H · U."""
    if np is None:
        raise RuntimeError("numpy required")
    return H @ U


def embed_cap_in_Ue(Ue, axis: str = "23", L_bias: int = 6, L_arm: int = 1, removed_endcap: bool = True):
    """Embed the Global-Frame cap transport inside the PP-generator for Ue.

    Returns (Ue_cap, meta) where:
      - Ue_cap := Ue · H†, with H = cap_holonomy(axis, ...)
      - This is algebraically equivalent to applying the same H as a Σ-holonomy on PMNS:
            (Ue_cap)† Uν  =  (Ue·H†)† Uν  =  H · (Ue†Uν)

    Deterministic, knob-free. Use removed_endcap=False as the sign-flip NEG.
    """
    if np is None:
        raise RuntimeError("numpy required")
    H, meta = cap_holonomy(axis=str(axis), L_bias=int(L_bias), L_arm=int(L_arm), removed_endcap=bool(removed_endcap))
    return (Ue @ H.conjugate().T), meta
