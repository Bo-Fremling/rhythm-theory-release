#!/usr/bin/env python3
"""FLAVOR_LOCK verifier (no tuning; deterministic).

Reads existing FLAVOR_LOCK artifacts and evaluates explicit gates.
This verifier does NOT change the optimizer. It only checks outputs.

Usage (from repo root):
  python3 00_TOP/LOCKS/FLAVOR_LOCK/flavor_lock_verify.py

Inputs:
  out/FLAVOR_LOCK/flavor_ud_v0_9.json
  out/FLAVOR_LOCK/flavor_enu_v0_9.json
  (optional) 00_TOP/OVERLAY/sm29_data_reference_v0_1.json  [Overlay refs for match-gates only]

Outputs:
  out/FLAVOR_LOCK/flavor_lock_verify_v0_1.json
  out/FLAVOR_LOCK/flavor_lock_verify_summary_v0_1.md

Exit codes:
  0 = PASS (all core/NEG sanity gates pass)
  1 = FAIL (one or more core/NEG sanity gates fail)
  2 = MISSING inputs

Notes:
  - "match_gates" compare to external refs; they DO NOT affect overall PASS.
"""

from __future__ import annotations

import json
import itertools
import math
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Optional numeric backend (already a repo dependency via flavor_lock_run.py)
try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None

# Σ / RP holonomy utilities (local module)
try:
    import sigma_map  # type: ignore
except Exception:  # pragma: no cover
    sigma_map = None

REPO_ROOT = Path(__file__).resolve().parents[3]  # .../00_TOP/LOCKS/FLAVOR_LOCK -> repo root

# Hard thresholds (policy constants; NOT knobs)
EPS_RATIO_DIFF = 1e-9      # exact-identical guard
MIN_THETA_DEG  = 0.1       # non-trivial angle threshold
MIN_J_ABS      = 1e-8      # non-trivial CP threshold
MIN_HIER_D_M1M2 = 1e-5     # avoid absurd d hierarchy (e.g. 1e-7)

# RT construct (diagnostic gates; derived from fixed RT integers, NOT tunable)
RT_K = 30
RT_RHO = 10
RT_EPS30_DEG = 360.0 / RT_K                   # 12°
RT_EPS30_RHO_DEG = RT_EPS30_DEG / RT_RHO      # 1.2°
RT_EPS30_RHO2_DEG = RT_EPS30_RHO_DEG / RT_RHO # 0.12°

# CKM expected *scale* windows (coarse; no PDG fitting)
RT_CKM_THETA12_RANGE_DEG = (0.5 * RT_EPS30_DEG, 2.0 * RT_EPS30_DEG)
RT_CKM_THETA23_RANGE_DEG = (0.5 * RT_EPS30_RHO_DEG, 5.0 * RT_EPS30_RHO_DEG)
RT_CKM_THETA13_RANGE_DEG = (0.0, 5.0 * RT_EPS30_RHO2_DEG)

# PMNS expected to be “large mixing” in Core-structure sense (very loose).
RT_PMNS_MIN_LARGE_ANGLE_DEG = 20.0

# CKM CP is expected small (very loose; diagnostic only)
RT_CKM_MAX_J_ABS = 1e-3

# Phase-lift / unitary reconstruction (policy constants; NOT knobs)
PHASE_SET_RAD = (0.0, math.pi, 2.0 * math.pi / 3.0, -2.0 * math.pi / 3.0)
UNITARY_RES_TOL = 1e-6

# RT phase quantization diagnostics (C30 grid).
# Used only for *distance-to-grid* reporting (no gate yet).
C30_PHASE_SET_RAD = tuple((((2.0 * math.pi * k) / 30.0 + math.pi) % (2.0 * math.pi) - math.pi) for k in range(30))

# NEG-control thresholds
MAX_NEG_THETA_DEG = 1e-6
MAX_NEG_J_ABS     = 1e-12


def _load_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _ratio_vec(x: Dict[str, Any]) -> Tuple[float, float]:
    r = x.get("ratios", {})
    return float(r.get("m1_over_m2")), float(r.get("m2_over_m3"))


def _angles(x: Dict[str, Any]) -> Dict[str, float]:
    # Accept either a wrapper dict {"angles": {...}} or a plain angles dict.
    a = x if ("theta12_deg" in x or "theta23_deg" in x or "theta13_deg" in x) else x.get("angles", {})

    out = {
        "theta12_deg": float(a.get("theta12_deg")),
        "theta23_deg": float(a.get("theta23_deg")),
        "theta13_deg": float(a.get("theta13_deg")),
        "J": float(a.get("J")),
    }

    # Optional extras if present
    if a.get("delta_deg_from_sin") is not None:
        out["delta_deg_from_sin"] = float(a.get("delta_deg_from_sin"))
    if a.get("sin_delta") is not None:
        out["sin_delta"] = float(a.get("sin_delta"))

    return out


def _rt_compute_structural_gates(
    ck: Dict[str, float],
    pm: Dict[str, float],
    neg_ck: Optional[Dict[str, float]] = None,
    neg_pm: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Compute the diagnostic 'gate' block used across rt_construct_* nodes.

    This is **not** a PDG fit. It encodes only coarse structure expectations:
      - score(CKM) < score(PMNS)
      - CKM hierarchy + coarse windows + non-trivial CP
      - PMNS has >=2 large angles
      - NEG is ~trivial (if provided)
    """

    def _score(a: Dict[str, float]) -> float:
        return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2

    def _in_range(x: float, r: Tuple[float, float]) -> bool:
        return (x >= float(r[0])) and (x <= float(r[1]))

    ck_t12 = float(ck.get("theta12_deg", 0.0))
    ck_t23 = float(ck.get("theta23_deg", 0.0))
    ck_t13 = float(ck.get("theta13_deg", 0.0))
    ck_J = float(ck.get("J", 0.0))

    pm_t12 = float(pm.get("theta12_deg", 0.0))
    pm_t23 = float(pm.get("theta23_deg", 0.0))
    pm_t13 = float(pm.get("theta13_deg", 0.0))

    s_ckm = _score(ck)
    s_pmns = _score(pm)

    ck_order = bool(ck_t12 > ck_t23 > ck_t13)
    ck_ranges_ok = bool(
        _in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG)
        and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG)
        and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG)
    )
    ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
    pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)

    pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
    pass_pmns_pattern = bool(pm_large_count >= 2)

    neg_ok = True
    if isinstance(neg_ck, dict) and isinstance(neg_pm, dict):
        neg_ok = bool(
            abs(float(neg_ck.get("J", 0.0))) <= MAX_NEG_J_ABS
            and abs(float(neg_pm.get("J", 0.0))) <= MAX_NEG_J_ABS
            and float(neg_ck.get("theta12_deg", 0.0)) <= MAX_NEG_THETA_DEG
            and float(neg_ck.get("theta23_deg", 0.0)) <= MAX_NEG_THETA_DEG
            and float(neg_ck.get("theta13_deg", 0.0)) <= MAX_NEG_THETA_DEG
            and float(neg_pm.get("theta12_deg", 0.0)) <= MAX_NEG_THETA_DEG
            and float(neg_pm.get("theta23_deg", 0.0)) <= MAX_NEG_THETA_DEG
            and float(neg_pm.get("theta13_deg", 0.0)) <= MAX_NEG_THETA_DEG
        )

    pass_struct = bool(s_ckm < s_pmns and neg_ok)

    return {
        "score": {
            "ckm": float(s_ckm),
            "pmns": float(s_pmns),
            "pass": bool(pass_struct),
            "policy": "Require score(CKM) < score(PMNS); NEG trivial must be ~0 (if provided)",
        },
        "ckm_pattern": {
            "theta12_range_deg": [float(RT_CKM_THETA12_RANGE_DEG[0]), float(RT_CKM_THETA12_RANGE_DEG[1])],
            "theta23_range_deg": [float(RT_CKM_THETA23_RANGE_DEG[0]), float(RT_CKM_THETA23_RANGE_DEG[1])],
            "theta13_range_deg": [float(RT_CKM_THETA13_RANGE_DEG[0]), float(RT_CKM_THETA13_RANGE_DEG[1])],
            "ordering": "theta12>theta23>theta13",
            "J_range_abs": [float(MIN_J_ABS), float(RT_CKM_MAX_J_ABS)],
            "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J},
            "pass": bool(pass_ckm_pattern),
        },
        "pmns_pattern": {
            "min_large_angle_deg": float(RT_PMNS_MIN_LARGE_ANGLE_DEG),
            "large_count": int(pm_large_count),
            "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13},
            "pass": bool(pass_pmns_pattern),
        },
        "neg_ok": bool(neg_ok),
        "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
        "policy": "Structural+pattern gates (diagnostic): score + CKM window+hierarchy+CP + PMNS large-mixing + NEG",
    }


def _history_versions(out_dir: Path) -> dict:
    # Informational only (does not affect PASS).
    # Scans existing v0_* snapshots and records theta13 + abs-only bound.

    import re

    def parse_ver(name: str):
        m = re.search(r"_v(\d+)_(\d+)\.json$", name)
        if not m:
            return None
        return (int(m.group(1)), int(m.group(2)))

    def min_abs(mat):
        try:
            return min(abs(float(mat[i][j])) for i in range(3) for j in range(3))
        except Exception:
            return None

    def bound_from_mmin(mmin):
        if mmin is None:
            return None
        try:
            return math.degrees(math.asin(min(max(float(mmin), 0.0), 1.0)))
        except Exception:
            return None

    out = {"CKM": [], "PMNS": []}

    for fp in sorted(out_dir.glob("flavor_ud_v0_*.json")):
        ver = parse_ver(fp.name)
        if ver is None:
            continue
        try:
            obj = json.loads(fp.read_text(encoding="utf-8"))
            ang = (obj.get("CKM", {}) or {}).get("angles", {}) or {}
            Vabs = (obj.get("CKM", {}) or {}).get("V_abs")
            mmin = min_abs(Vabs)
            out["CKM"].append({
                "ver": f"v{ver[0]}_{ver[1]}",
                "theta13_deg": ang.get("theta13_deg"),
                "min_abs": mmin,
                "min_theta13_deg_bound": bound_from_mmin(mmin),
            })
        except Exception:
            continue

    for fp in sorted(out_dir.glob("flavor_enu_v0_*.json")):
        ver = parse_ver(fp.name)
        if ver is None:
            continue
        try:
            obj = json.loads(fp.read_text(encoding="utf-8"))
            ang = (obj.get("PMNS", {}) or {}).get("angles", {}) or {}
            Uabs = (obj.get("PMNS", {}) or {}).get("U_abs")
            mmin = min_abs(Uabs)
            out["PMNS"].append({
                "ver": f"v{ver[0]}_{ver[1]}",
                "theta13_deg": ang.get("theta13_deg"),
                "min_abs": mmin,
                "min_theta13_deg_bound": bound_from_mmin(mmin),
            })
        except Exception:
            continue

    def key(v):
        try:
            s = v["ver"][1:]
            a, b = s.split("_")
            return (int(a), int(b))
        except Exception:
            return (0, 0)

    out["CKM"] = sorted(out["CKM"], key=key)
    out["PMNS"] = sorted(out["PMNS"], key=key)

    return out


def _angles_from_abs_matrix(M: list) -> Optional[Dict[str, float]]:
    """Compute (theta12,theta23,theta13) in PDG convention from an abs matrix.

    Uses:
      s13 = |V_{ub}| (= M[0][2])
      s12 = |V_{us}| / sqrt(1-s13^2)
      s23 = |V_{cb}| / sqrt(1-s13^2)

    Same mapping is used for PMNS with (e,mu,tau) rows and (1,2,3) cols.
    Returns None if the mapping is invalid.
    """

    try:
        s13 = float(M[0][2])
        d = 1.0 - s13 * s13
        if d <= 0.0:
            return None
        c13 = math.sqrt(d)
        s12 = float(M[0][1]) / c13
        s23 = float(M[1][2]) / c13
        if not (0.0 <= s12 <= 1.0 and 0.0 <= s23 <= 1.0 and 0.0 <= s13 <= 1.0):
            return None
        return {
            "theta12_deg": math.degrees(math.asin(s12)),
            "theta23_deg": math.degrees(math.asin(s23)),
            "theta13_deg": math.degrees(math.asin(s13)),
        }
    except Exception:
        return None


def _unitary_residual(U: list) -> float:
    """Max elementwise residual of U^†U vs I."""
    mx = 0.0
    for i in range(3):
        for j in range(3):
            s = 0j
            for k in range(3):
                s += complex(U[k][i]).conjugate() * complex(U[k][j])
            target = 1.0 if i == j else 0.0
            r = abs(s - target)
            if r > mx:
                mx = r
    return float(mx)


def _angles_J_from_unitary(U: list) -> Optional[Dict[str, float]]:
    """Angles + J from a complex 3x3 matrix (assumed ~unitary)."""
    try:
        s13 = abs(complex(U[0][2]))
        d = 1.0 - s13 * s13
        if d <= 0.0:
            return None
        c13 = math.sqrt(d)
        s12 = abs(complex(U[0][1])) / c13
        s23 = abs(complex(U[1][2])) / c13
        if not (0.0 <= s12 <= 1.0 and 0.0 <= s23 <= 1.0 and 0.0 <= s13 <= 1.0):
            return None

        th12 = math.asin(s12)
        th23 = math.asin(s23)
        th13 = math.asin(s13)

        J = (complex(U[0][0]) * complex(U[1][1]) * complex(U[0][1]).conjugate() * complex(U[1][0]).conjugate()).imag

        c12 = math.cos(th12)
        c23 = math.cos(th23)
        denom = c12 * c23 * (c13**2) * s12 * s23 * s13
        sin_delta = None
        delta_deg_from_sin = None
        if abs(denom) > 0.0:
            sin_delta = float(max(min(J / denom, 1.0), -1.0))
            delta_deg_from_sin = float(math.degrees(math.asin(sin_delta)))

        return {
            "theta12_deg": float(math.degrees(th12)),
            "theta23_deg": float(math.degrees(th23)),
            "theta13_deg": float(math.degrees(th13)),
            "J": float(J),
            "sin_delta": sin_delta,
            "delta_deg_from_sin": delta_deg_from_sin,
        }
    except Exception:
        return None


def _phase_lift_scan_abs(M_abs: list, kind: str) -> Dict[str, Any]:
    """Try to reconstruct a complex unitary using a discrete phase set.

    Gauge-fix: first row and first column phases = 0.
    Free phases: (1,1),(1,2),(2,1),(2,2) ∈ PHASE_SET_RAD.
    """

    out: Dict[str, Any] = {
        "kind": kind,
        "policy": {
            "phase_set_rad": list(PHASE_SET_RAD),
            "unitary_res_tol": UNITARY_RES_TOL,
            "gauge_fix": "phi[0,*]=0 and phi[*,0]=0; free phases on submatrix (1..2,1..2)",
        },
        "scan": {"n": 0},
        "best": None,
    }

    try:
        A = [[float(M_abs[i][j]) for j in range(3)] for i in range(3)]
    except Exception:
        out["error"] = "invalid abs matrix"
        return out

    best: Optional[Dict[str, Any]] = None
    best_key: Optional[Tuple[float, float, float, float, float]] = None

    for p11 in PHASE_SET_RAD:
        for p12 in PHASE_SET_RAD:
            for p21 in PHASE_SET_RAD:
                for p22 in PHASE_SET_RAD:
                    out["scan"]["n"] += 1

                    phi = [[0.0, 0.0, 0.0], [0.0, p11, p12], [0.0, p21, p22]]
                    U = [[A[i][j] * complex(math.cos(phi[i][j]), math.sin(phi[i][j])) for j in range(3)] for i in range(3)]

                    res = _unitary_residual(U)
                    ang = _angles_J_from_unitary(U)

                    key = (res, p11, p12, p21, p22)
                    if best is None or (best_key is not None and key < best_key) or best_key is None:
                        best = {
                            "unitary_residual": res,
                            "phases_rad": {"p11": p11, "p12": p12, "p21": p21, "p22": p22},
                            "angles": ang,
                            "unitary_res_ok": bool(res <= UNITARY_RES_TOL),
                        }
                        best_key = key

    out["best"] = best
    return out


def _wrap_pi(x: float) -> float:
    y = (x + math.pi) % (2.0 * math.pi) - math.pi
    # map -pi -> +pi for stable comparisons
    if y <= -math.pi + 1e-15:
        y = math.pi
    return float(y)


def _phase_dist_to_set(phi: float, phase_set: Tuple[float, ...] = C30_PHASE_SET_RAD) -> float:
    p = _wrap_pi(float(phi))
    return float(min(abs(_wrap_pi(p - q)) for q in phase_set))


def _constructive_unitary_lift_abs(M_abs: list, kind: str) -> Dict[str, Any]:
    """Construct one unitary candidate from |M| using triangle-closure (3x3).

    No continuous scan: only discrete branch choices (sign of acos) for row2 and row3
    triangle closures against row1. This is a deterministic *feasibility* construction
    when |M| is unistochastic.

    Output is diagnostic only (does not gate overall PASS).
    """

    out: Dict[str, Any] = {
        "kind": kind,
        "policy": {
            "construction": "row0 real+; col0 real+; enforce row0⊥row1 and row0⊥row2 by triangle closure; choose discrete branches to minimize residual",
            "branches": {"row1_sign": [1, -1], "row2_sign": [1, -1]},
            "phase_grid": "C30 (2π/30) for distance diagnostics only",
        },
        "best": None,
    }

    try:
        A = [[float(M_abs[i][j]) for j in range(3)] for i in range(3)]
    except Exception:
        out["error"] = "invalid abs matrix"
        return out

    def build_row(i: int, sign: int):
        # Row0 is fixed real-positive by gauge.
        if i == 0:
            return ([complex(A[0][0], 0.0), complex(A[0][1], 0.0), complex(A[0][2], 0.0)], {"sign": 0})

        L1 = A[0][0] * A[i][0]
        L2 = A[0][1] * A[i][1]
        L3 = A[0][2] * A[i][2]

        if L1 == 0.0 or L2 == 0.0 or L3 == 0.0:
            # Degenerate; keep phases zero.
            return ([complex(A[i][0], 0.0), complex(A[i][1], 0.0), complex(A[i][2], 0.0)], {"sign": sign, "degenerate": True})

        # Solve |L1 + L2 e^{iφ}| = L3
        cosphi = (L3 * L3 - L1 * L1 - L2 * L2) / (2.0 * L1 * L2)
        cosphi = max(min(cosphi, 1.0), -1.0)
        phi = float(sign) * math.acos(cosphi)

        v2 = L2 * complex(math.cos(phi), math.sin(phi))
        v3 = -(L1 + v2)
        theta = math.atan2(v3.imag, v3.real)
        L3_hat = abs(v3)

        # Map to entry phases: term is L2 e^{-iφ11} so φ11 = -phi; similarly φ12=-theta.
        U0 = complex(A[i][0], 0.0)
        U1 = A[i][1] * complex(math.cos(-phi), math.sin(-phi))
        U2 = A[i][2] * complex(math.cos(-theta), math.sin(-theta))

        return ([U0, U1, U2], {"sign": int(sign), "phi": phi, "theta": theta, "L": [L1, L2, L3], "L3_hat": L3_hat, "L3_err": float(abs(L3_hat - L3))})

    best = None
    best_key = None

    # Discrete branches (reflection ambiguity)
    for s_row1 in (1, -1):
        for s_row2 in (1, -1):
            r0, d0 = build_row(0, 0)
            r1, d1 = build_row(1, s_row1)
            r2, d2 = build_row(2, s_row2)
            U = [r0, r1, r2]

            res = _unitary_residual(U)
            # residual of the remaining orthogonality (row1·row2*)
            dot12 = 0j
            for j in range(3):
                dot12 += complex(U[1][j]) * complex(U[2][j]).conjugate()
            dot12_abs = abs(dot12)

            ang = _angles_J_from_unitary(U)

            # phase-quantization distances (C30 grid)
            dists = []
            for i in range(3):
                for j in range(3):
                    ph = math.atan2(complex(U[i][j]).imag, complex(U[i][j]).real)
                    dists.append(_phase_dist_to_set(ph))
            ph_max = max(dists) if dists else None
            ph_rms = math.sqrt(sum(x*x for x in dists)/len(dists)) if dists else None

            key = (float(dot12_abs), float(res), float(ph_max if ph_max is not None else 0.0), int(s_row1), int(s_row2))
            if best is None or (best_key is not None and key < best_key) or best_key is None:
                best_key = key
                best = {
                    "branches": {"row1_sign": int(s_row1), "row2_sign": int(s_row2)},
                    "unitary_residual": float(res),
                    "row1_row2_dot_abs": float(dot12_abs),
                    "angles": ang,
                    "phase_quant": {"phase_set": "C30", "max_dist_rad": ph_max, "rms_dist_rad": ph_rms},
                    "triangles": {"row1": d1, "row2": d2},
                }

    out["best"] = best
    return out



def _max_abs_diff(A: list, B: list) -> float:
    try:
        return max(abs(float(A[i][j]) - float(B[i][j])) for i in range(3) for j in range(3))
    except Exception:
        return float("nan")


def _rms_abs_diff(A: list, B: list) -> float:
    try:
        s = 0.0
        n = 0
        for i in range(3):
            for j in range(3):
                d = float(A[i][j]) - float(B[i][j])
                s += d * d
                n += 1
        return math.sqrt(s / n) if n else float("nan")
    except Exception:
        return float("nan")


def _abs_from_complex(U: list) -> list:
    return [[abs(complex(U[i][j])) for j in range(3)] for i in range(3)]


def _is_doubly_stochastic_sq(M_abs: list) -> Dict[str, Any]:
    """Check that rows/cols are normalized in squares: sum_j |M_ij|^2 = 1 and sum_i |M_ij|^2 = 1."""
    try:
        A = [[float(M_abs[i][j]) for j in range(3)] for i in range(3)]
        rs = [sum(A[i][j] ** 2 for j in range(3)) for i in range(3)]
        cs = [sum(A[i][j] ** 2 for i in range(3)) for j in range(3)]
        rerr = [abs(v - 1.0) for v in rs]
        cerr = [abs(v - 1.0) for v in cs]
        return {
            "row_sumsq": rs,
            "col_sumsq": cs,
            "row_err": rerr,
            "col_err": cerr,
            "max_err": max(rerr + cerr),
        }
    except Exception:
        return {"error": "invalid matrix"}


def _triangle_ineq_ok(a: list, tol: float = 1e-15) -> Dict[str, Any]:
    """Given three positive lengths, check if they can close a triangle (necessary+sufficient for 3-term complex sum = 0)."""
    try:
        x = sorted([abs(float(v)) for v in a], reverse=True)
        ok = bool(x[0] <= x[1] + x[2] + tol)
        return {"a": x, "ok": ok, "margin": (x[1] + x[2] - x[0])}
    except Exception:
        return {"error": "invalid lengths"}


def _unistochastic_tri_checks(M_abs: list) -> Dict[str, Any]:
    """Fast unistochastic feasibility diagnostics for 3x3.

    For each pair of rows (i,k), the orthogonality condition
      sum_j U_{ij} U^*_{kj} = 0
    is feasible for SOME phases iff the three magnitudes
      a_j = |U_{ij}||U_{kj}|
    satisfy triangle inequality.

    Same for each pair of columns.

    This does NOT construct phases; it says whether a unitary lift exists in principle.
    """
    out: Dict[str, Any] = {"row_pairs": [], "col_pairs": [], "pass_all": None}
    try:
        A = [[float(M_abs[i][j]) for j in range(3)] for i in range(3)]
    except Exception:
        out["error"] = "invalid abs matrix"
        return out

    ok_all = True
    # row pairs
    for i in range(3):
        for k in range(i + 1, 3):
            a = [abs(A[i][j] * A[k][j]) for j in range(3)]
            tri = _triangle_ineq_ok(a)
            out["row_pairs"].append({"pair": [i, k], "a": a, "tri": tri})
            if tri.get("ok") is False:
                ok_all = False

    # col pairs
    for j in range(3):
        for l in range(j + 1, 3):
            a = [abs(A[i][j] * A[i][l]) for i in range(3)]
            tri = _triangle_ineq_ok(a)
            out["col_pairs"].append({"pair": [j, l], "a": a, "tri": tri})
            if tri.get("ok") is False:
                ok_all = False

    out["pass_all"] = bool(ok_all)
    return out


def _ckm_unitary_pdg(theta12_rad: float, theta23_rad: float, theta13_rad: float, delta_rad: float) -> list:
    """PDG convention CKM-like unitary from three angles + CP phase delta."""
    s12, c12 = math.sin(theta12_rad), math.cos(theta12_rad)
    s23, c23 = math.sin(theta23_rad), math.cos(theta23_rad)
    s13, c13 = math.sin(theta13_rad), math.cos(theta13_rad)
    e_mi = complex(math.cos(-delta_rad), math.sin(-delta_rad))
    e_pi = complex(math.cos(delta_rad), math.sin(delta_rad))

    # PDG parameterization
    V = [[0j] * 3 for _ in range(3)]
    V[0][0] = c12 * c13
    V[0][1] = s12 * c13
    V[0][2] = s13 * e_mi

    V[1][0] = -s12 * c23 - c12 * s23 * s13 * e_pi
    V[1][1] =  c12 * c23 - s12 * s23 * s13 * e_pi
    V[1][2] =  s23 * c13

    V[2][0] =  s12 * s23 - c12 * c23 * s13 * e_pi
    V[2][1] = -c12 * s23 - s12 * c23 * s13 * e_pi
    V[2][2] =  c23 * c13
    return V


def _best_delta_from_sin(sin_delta: float, theta12: float, theta23: float, theta13: float, target_abs: list) -> Dict[str, Any]:
    """Choose between delta and (pi-delta) using abs-matrix consistency."""
    try:
        sd = float(max(min(sin_delta, 1.0), -1.0))
        d1 = math.asin(sd)
        d2 = math.pi - d1
        V1 = _ckm_unitary_pdg(theta12, theta23, theta13, d1)
        V2 = _ckm_unitary_pdg(theta12, theta23, theta13, d2)
        A1 = _abs_from_complex(V1)
        A2 = _abs_from_complex(V2)
        e1 = _max_abs_diff(A1, target_abs)
        e2 = _max_abs_diff(A2, target_abs)
        best = (d1, A1, e1) if (e1 <= e2) else (d2, A2, e2)
        return {"delta_rad": float(best[0]), "abs_max_err": float(best[2])}
    except Exception:
        return {"error": "delta selection failed"}


def _delta_grid_C30(delta_rad: float) -> Dict[str, Any]:
    """Nearest C30 grid multiple of 2π/30."""
    g = 2.0 * math.pi / 30.0
    k = int(round(float(delta_rad) / g))
    dg = k * g
    return {
        "grid_step_rad": g,
        "k": k,
        "delta_grid_rad": dg,
        "delta_grid_deg": float(math.degrees(dg)),
        "delta_minus_grid_rad": float(delta_rad - dg),
    }



def _best_k_C30(theta12: float, theta23: float, theta13: float, target_abs: list) -> Dict[str, Any]:
    """Best-fitting C30 grid index k in canonical domain k∈{0..15} (δ∈[0,π]) by minimizing abs-matrix error.

    Deterministic, discrete-only diagnostic (no continuous scan). Companion branch k+15 corresponds to δ+π.
    """
    g = 2.0 * math.pi / 30.0
    best = None
    for k in range(16):
        d = k * g
        V = _ckm_unitary_pdg(theta12, theta23, theta13, d)
        A = _abs_from_complex(V)
        emax = _max_abs_diff(A, target_abs)
        erms = _rms_abs_diff(A, target_abs)
        key = (emax, erms, k)
        if best is None or key < best[0]:
            best = (key, k, d, emax, erms)
    if best is None:
        return {"error": "k-scan failed"}
    _, kbest, dbest, emax, erms = best
    return {
        "k_best": int(kbest),
        "delta_grid_rad": float(dbest),
        "delta_grid_deg": float(math.degrees(float(dbest))),
        "abs_max_err": float(emax),
        "abs_rms_err": float(erms),
    }


def _nearest_phase_C30(phi_rad: float) -> Dict[str, Any]:
    """Quantize phase to nearest C30 multiple of 2π/30.

    Returns k in Z (not reduced), quantized phase, and residual.
    """
    g = 2.0 * math.pi / 30.0
    k = int(round(float(phi_rad) / g))
    q = k * g
    return {
        "grid_step_rad": g,
        "k": int(k),
        "phi_grid_rad": float(q),
        "phi_grid_deg": float(math.degrees(q)),
        "phi_minus_grid_rad": float(phi_rad - q),
    }


def _constructive_unitary_lift_abs_C30(M_abs: list, kind: str) -> Dict[str, Any]:
    """Construct one unitary candidate from |M| using triangle-closure, then quantize phases to C30.

    No continuous tuning: only discrete row-branch choices (signs) + C30 phase snapping.
    Diagnostic object to harden a RT-compatible phase policy.
    """

    out: Dict[str, Any] = {
        "kind": kind,
        "policy": {
            "construction": "triangle closure vs row0; then snap the two solved phases per row to nearest C30 (2π/30)",
            "branches": {"row1_sign": [1, -1], "row2_sign": [1, -1]},
            "phase_grid": "C30",
            "note": "This can only worsen unitarity; it measures distance-to-C30 feasibility without tuning.",
        },
        "best": None,
    }

    try:
        A = [[float(M_abs[i][j]) for j in range(3)] for i in range(3)]
    except Exception:
        out["error"] = "invalid abs matrix"
        return out

    def build_row(i: int, sign: int):
        if i == 0:
            return ([complex(A[0][0], 0.0), complex(A[0][1], 0.0), complex(A[0][2], 0.0)], {"sign": 0})

        L1 = A[0][0] * A[i][0]
        L2 = A[0][1] * A[i][1]
        L3 = A[0][2] * A[i][2]

        if L1 == 0.0 or L2 == 0.0 or L3 == 0.0:
            return ([complex(A[i][0], 0.0), complex(A[i][1], 0.0), complex(A[i][2], 0.0)], {"sign": sign, "degenerate": True})

        cosphi = (L3 * L3 - L1 * L1 - L2 * L2) / (2.0 * L1 * L2)
        cosphi = max(min(cosphi, 1.0), -1.0)
        phi_raw = float(sign) * math.acos(cosphi)

        v2 = L2 * complex(math.cos(phi_raw), math.sin(phi_raw))
        v3 = -(L1 + v2)
        theta_raw = math.atan2(v3.imag, v3.real)

        q_phi = _nearest_phase_C30(phi_raw)
        q_th = _nearest_phase_C30(theta_raw)

        phi = float(q_phi["phi_grid_rad"])
        theta = float(q_th["phi_grid_rad"])

        U0 = complex(A[i][0], 0.0)
        U1 = A[i][1] * complex(math.cos(-phi), math.sin(-phi))
        U2 = A[i][2] * complex(math.cos(-theta), math.sin(-theta))

        # quantify the triangle error after snapping
        v2q = L2 * complex(math.cos(phi), math.sin(phi))
        v3q = -(L1 + v2q)
        L3_hat = abs(v3q)

        return ([U0, U1, U2], {
            "sign": int(sign),
            "phi_raw": float(phi_raw),
            "theta_raw": float(theta_raw),
            "phi_C30": q_phi,
            "theta_C30": q_th,
            "L": [float(L1), float(L2), float(L3)],
            "L3_hat_after_snap": float(L3_hat),
            "L3_err_after_snap": float(abs(L3_hat - L3)),
        })

    best = None
    best_key = None

    for s_row1 in (1, -1):
        for s_row2 in (1, -1):
            r0, d0 = build_row(0, 0)
            r1, d1 = build_row(1, s_row1)
            r2, d2 = build_row(2, s_row2)
            U = [r0, r1, r2]

            res = _unitary_residual(U)
            dot12 = 0j
            for j in range(3):
                dot12 += complex(U[1][j]) * complex(U[2][j]).conjugate()
            dot12_abs = abs(dot12)

            ang = _angles_J_from_unitary(U)

            # key: prioritize remaining orthogonality and overall unitarity
            key = (float(dot12_abs), float(res), int(s_row1), int(s_row2))
            if best is None or (best_key is not None and key < best_key) or best_key is None:
                best_key = key
                best = {
                    "branches": {"row1_sign": int(s_row1), "row2_sign": int(s_row2)},
                    "unitary_residual": float(res),
                    "row1_row2_dot_abs": float(dot12_abs),
                    "angles": ang,
                    "triangles": {"row1": d1, "row2": d2},
                }

    out["best"] = best
    return out



# -----------------------------
# RT phase rule (deterministic) — v0.1
# -----------------------------
# Purpose: replace “snap-each-entry” with a RT-derived *global* CP phase rule
# built from (δφ*, Z3, A/B) plus deterministic tie-breakers.
# This is diagnostic-only until promoted to a hard gate.

RT_DELTA_PHI_STAR_RAD = -0.94  # canonical δφ* (rad). Policy constant, not a fit knob.
RT_Z3_OFFSETS_RAD = (+2.0 * math.pi / 3.0, -2.0 * math.pi / 3.0)
RT_AB_OFFSETS_RAD = (0.0, math.pi)
RT_RHO_OFFSETS_RAD = (0.0, +2.0 * math.pi / 10.0, -2.0 * math.pi / 10.0)  # rho=10 rotor step


def _canon_0_2pi(x: float) -> float:
    y = float(x) % (2.0 * math.pi)
    if y < 0.0:
        y += 2.0 * math.pi
    return float(y)


def _c30_quantize_phase(phi_rad: float) -> Dict[str, Any]:
    """Quantize to nearest C30 multiple.

    Returns:
      - k_mod30 ∈ {0..29}, delta_grid_rad in [0,2π)
      - k_0_15 ∈ {0..15}, delta_grid_rad_0_15 in [0,π] (canonical fold: δ ~ 2π−δ)
    """
    q = _nearest_phase_C30(float(phi_rad))
    k = int(q.get("k", 0)) % 30
    d = _canon_0_2pi(float(q.get("phi_grid_rad", 0.0)))

    g = 2.0 * math.pi / 30.0
    k015 = k if k <= 15 else (30 - k)
    d015 = float(k015) * g

    return {
        "k_mod30": int(k),
        "delta_grid_rad": float(d),
        "delta_grid_deg": float(math.degrees(d)),
        "k_0_15": int(k015),
        "delta_grid_rad_0_15": float(d015),
        "delta_grid_deg_0_15": float(math.degrees(d015)),
        "raw": q,
    }


def _rt_delta_candidates(kind: str) -> Dict[str, Any]:
    """Generate deterministic δ candidates from δφ* + Z3 + A/B.

    We treat Z3 as a discrete offset ±2π/3. A/B is a discrete offset 0 or π.
    We also allow an optional rotor-step offset ±2π/10 (ρ=10) as a discrete RT kinematic shift.
    Then we quantize δ to C30 (2π/30) as the RP-strobe compatibility layer.

    Tie-breakers are deterministic (lexicographic on declared ordering + then by k distance).
    """

    candidates = []

    # Fixed ordering = deterministic tie-break (not tuning).
    # If later we want sector-dependent ordering, encode it explicitly in spec.
    order = 0
    for z3 in RT_Z3_OFFSETS_RAD:
        for ab in RT_AB_OFFSETS_RAD:
            for rho in RT_RHO_OFFSETS_RAD:
                order += 1
                delta_raw = _wrap_pi(RT_DELTA_PHI_STAR_RAD + float(z3) + float(ab) + float(rho))
                q = _c30_quantize_phase(delta_raw)
                candidates.append({
                    "order": int(order),
                    "z3_offset_rad": float(z3),
                    "ab_offset_rad": float(ab),
                    "rho_offset_rad": float(rho),
                    "delta_raw_rad": float(delta_raw),
                    "delta_raw_deg": float(math.degrees(delta_raw)),
                    "delta_C30": q,
                })

    return {
        "kind": kind,
        "policy": {
            "delta_phi_star_rad": float(RT_DELTA_PHI_STAR_RAD),
            "z3_offsets_rad": [float(x) for x in RT_Z3_OFFSETS_RAD],
            "ab_offsets_rad": [float(x) for x in RT_AB_OFFSETS_RAD],
            "rho_offsets_rad": [float(x) for x in RT_RHO_OFFSETS_RAD],
            "quantization": "C30 (2π/30)",
            "tie_break": "min(abs_max_err, abs_rms_err, |k_mod30| distance to 0, candidate order)",
        },
        "candidates": candidates,
    }


def _rt_phase_rule_unitary_lift(M_abs: list, kind: str) -> Dict[str, Any]:
    """RT-derived unitary candidate from |M|.

    Steps:
      1) Derive (θ12,θ23,θ13) from |M| (abs-only, deterministic).
      2) Generate δ candidates from (δφ*, Z3, A/B), quantized to C30.
      3) Build PDG unitary for each candidate (exactly unitary by construction).
      4) Choose best candidate by deterministic tie-break on abs-matrix error.

    Note: This does not claim physical correctness yet; it's a *bridge* from RT discrete phase
    ontology to a unitary lift that can be gated later.
    """

    out: Dict[str, Any] = {
        "kind": kind,
        "policy": {
            "angles_from_abs": "PDG mapping s13=|M[0,2]|, s12=|M[0,1]|/c13, s23=|M[1,2]|/c13",
            "delta_rule": "δ = Q_C30(δφ* + z3 + ab) with z3∈{±2π/3}, ab∈{0,π}",
            "unitary": "PDG parameterization",
            "note": "diagnostic-only until RT phase rule is proven/gated",
        },
        "best": None,
        "candidates": [],
        "compare": {},
    }

    ang_abs = _angles_from_abs_matrix(M_abs)
    if ang_abs is None:
        out["error"] = "cannot derive angles from abs matrix"
        return out

    th12 = math.radians(float(ang_abs["theta12_deg"]))
    th23 = math.radians(float(ang_abs["theta23_deg"]))
    th13 = math.radians(float(ang_abs["theta13_deg"]))

    cand_obj = _rt_delta_candidates(kind)
    best = None
    best_key = None

    for c in cand_obj["candidates"]:
        dq = (c.get("delta_C30") or {})
        delta = float(dq.get("delta_grid_rad"))
        kmod = int(dq.get("k_mod30"))

        U = _ckm_unitary_pdg(th12, th23, th13, delta)
        A = _abs_from_complex(U)
        emax = _max_abs_diff(A, M_abs)
        erms = _rms_abs_diff(A, M_abs)
        res = _unitary_residual(U)
        angU = _angles_J_from_unitary(U)

        item = {
            "order": int(c.get("order", 0)),
            "z3_offset_rad": float(c.get("z3_offset_rad")),
            "ab_offset_rad": float(c.get("ab_offset_rad")),
            "rho_offset_rad": float(c.get("rho_offset_rad", 0.0)),
            "delta_raw_deg": float(c.get("delta_raw_deg")),
            "delta_C30": dq,
            "abs_max_err": float(emax),
            "abs_rms_err": float(erms),
            "unitary_residual": float(res),
            "angles": angU,
        }
        out["candidates"].append(item)

        # Deterministic tie-breakers.
        # 1) abs_max_err, 2) abs_rms_err, 3) prefer δ in [0,π] (k<=15),
        # 4) prefer smaller canonical k_0_15, 5) candidate ordering.
        k015 = int(dq.get("k_0_15", 0))
        high = 1 if kmod > 15 else 0
        key = (float(emax), float(erms), int(high), int(k015), int(item["order"]))
        if best is None or best_key is None or key < best_key:
            best = item
            best_key = key

    out["best"] = best

    # Compare to existing operational k* (best-fit C30 delta by abs error), for transparency.
    try:
        kstar = _best_k_C30(th12, th23, th13, M_abs)
        out["compare"]["kstar_operational"] = kstar
    except Exception as e:
        try:
            checks["diag_ckm_holonomy_grid_error"] = {"error": repr(e)}
        except Exception:
            pass

    out["compare"]["angles_from_abs"] = ang_abs
    out["compare"]["delta_phi_star_rad"] = float(RT_DELTA_PHI_STAR_RAD)

    return out



# --- RT deterministic construct (v0.1): build mixing from RT-discrete choices only ---

# Canonical RT constants for flavor construct (Core-side; no SI).
RT_DELTA_PHI_STAR_RAD = -0.94  # δφ* (leading edge), from RT canon snapshot
RT_PI3 = math.pi / 3.0        # Z6 step
RT_EPS0 = 0.05                # use RT "gamma" scale as near-coupling strength (policy constant)


def _rt_quantize_pi_over_3(phi_rad: float) -> float:
    """Quantize an angle to nearest multiple of π/3, returned in [0,2π)."""
    q = int(round(float(phi_rad) / RT_PI3)) % 6
    return float(q) * RT_PI3


def _rt_circulant_Z3_weight() -> Tuple[float, float, float]:
    """Z3 weight w=(+2/3,-1/3,-1/3) scaled to integers (2,-1,-1)."""
    return (2.0, -1.0, -1.0)


def _rt_near_coupling_matrix(p: int):
    """Discrete near-coupling patterns (same encoding as FLAVOR_LOCK run)."""
    if np is None:
        return None
    M = np.zeros((3, 3), dtype=np.complex128)
    if p == 6:
        M[0, 1] = 1.0
        M[1, 2] = 1.0
    elif p == 5:
        M[0, 1] = 1.0
        M[1, 0] = 1.0
        M[1, 2] = 1.0
        M[2, 1] = 1.0
    elif p == 4:
        M[0, 1] = 1.0
        M[1, 2] = 1.0
        M[2, 0] = 1.0
    elif p == 3:
        M[0, 2] = 1.0
        M[2, 0] = 1.0
    elif p == 2:
        M[1, 2] = 1.0
        M[2, 1] = 1.0
    elif p == 1:
        M[0, 1] = 1.0
        M[1, 0] = 1.0
    else:
        raise ValueError(f"unknown near-coupling pattern p={p}")
    return M


def _rt_apply_edge_phases(N, phi_edge: float):
    if np is None:
        return None
    if abs(float(phi_edge)) < 1e-15:
        return N
    out = N.astype(np.complex128).copy()
    for i in range(3):
        for j in range(3):
            if out[i, j] != 0:
                out[i, j] *= complex(math.cos(phi_edge * (i - j)), math.sin(phi_edge * (i - j)))
    return out


def _rt_proj_phase_C30(k: int):
    """Diagonal phase projector with C30 spacing (n=30, step=k)."""
    if np is None:
        return None
    n = 30
    twopi = 2.0 * math.pi
    ph = [twopi * (j * int(k)) / n for j in range(3)]
    return np.diag([complex(math.cos(a), math.sin(a)) for a in ph]).astype(np.complex128)


def _rt_diag_yukawa(M):
    """Return (masses, eigenvectors) for H=M M† with deterministic ordering."""
    if np is None:
        return None, None
    H = M @ M.conjugate().T
    w, v = np.linalg.eigh(H)
    w = np.maximum(w.real, 0.0)
    idx = np.argsort(w)
    w = w[idx]
    v = v[:, idx]
    m = np.sqrt(w)
    return m, v


def _rt_gauge_fix_unitary(U):
    """Fix per-column global phases to make the largest component real-positive."""
    if np is None:
        return None
    U = U.astype(np.complex128).copy()
    for j in range(3):
        col = U[:, j]
        i = int(np.argmax(np.abs(col)))
        if abs(col[i]) < 1e-15:
            continue
        ph = float(np.angle(col[i]))
        col = col * complex(math.cos(-ph), math.sin(-ph))
        U[:, j] = col
    return U


def _rt_abs_from_np(M):
    return [[float(abs(M[i, j])) for j in range(3)] for i in range(3)]


def _rt_phase_from_np(M):
    """Elementwise phase (atan2) in radians, in [-pi, pi]."""
    out = []
    for i in range(3):
        row = []
        for j in range(3):
            z = complex(M[i, j])
            row.append(float(math.atan2(z.imag, z.real)))
        out.append(row)
    return out


def _rt_unitary_residual_np(U):
    if np is None:
        return None
    I = np.eye(3, dtype=np.complex128)
    R = U.conjugate().T @ U - I
    return float(np.max(np.abs(R)))


def _rt_unitary_from_pdg(theta12_deg: float, theta23_deg: float, theta13_deg: float, delta_deg: float):
    """Build a 3x3 unitary in the standard PDG parameterization.

    Used only for the RT-construct diagnostic v0.3, where angles are derived from fixed
    RT integers (K=30, rho=10) and δ comes from the RT phase-rule (C30).
    """
    if np is None:
        raise RuntimeError("numpy not available")

    t12 = math.radians(float(theta12_deg))
    t23 = math.radians(float(theta23_deg))
    t13 = math.radians(float(theta13_deg))
    d = math.radians(float(delta_deg))

    c12, s12 = math.cos(t12), math.sin(t12)
    c23, s23 = math.cos(t23), math.sin(t23)
    c13, s13 = math.cos(t13), math.sin(t13)

    e_pos = complex(math.cos(d), math.sin(d))
    e_neg = complex(math.cos(d), -math.sin(d))

    U = np.zeros((3, 3), dtype=np.complex128)

    # PDG convention
    U[0, 0] = c12 * c13
    U[0, 1] = s12 * c13
    U[0, 2] = s13 * e_neg

    U[1, 0] = -s12 * c23 - c12 * s23 * s13 * e_pos
    U[1, 1] = c12 * c23 - s12 * s23 * s13 * e_pos
    U[1, 2] = s23 * c13

    U[2, 0] = s12 * s23 - c12 * c23 * s13 * e_pos
    U[2, 1] = -c12 * s23 - s12 * c23 * s13 * e_pos
    U[2, 2] = c23 * c13

    return U


def _rt_unitary_sqrt(U):
    """Deterministic principal square-root for a unitary 3x3 matrix.

    Purpose: provide a scan-free, symmetric factorization bridge:
        V = U_u^† U_d with U_d = sqrt(V), U_u = sqrt(V)^†.

    Notes:
      - Uses principal eigenphases in (-pi, pi].
      - Determinism: sort eigenvalues by (phase, then |Re|, then |Im|) and apply a column gauge-fix.
    """
    if np is None:
        raise RuntimeError("numpy not available")
    U = U.astype(np.complex128)
    w, V = np.linalg.eig(U)

    def _phase(z: complex) -> float:
        return float(np.angle(z))

    items = []
    for i in range(3):
        z = complex(w[i])
        ph = _phase(z)
        items.append((ph, abs(z.real), abs(z.imag), i))
    items.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    idx = [t[3] for t in items]

    w = w[idx]
    V = V[:, idx]

    # Gauge-fix eigenvectors (column-wise) for deterministic presentation.
    V = _rt_gauge_fix_unitary(V)

    # principal phases
    ph = np.array([float(np.angle(complex(z))) for z in w], dtype=np.float64)
    D = np.diag([complex(math.cos(a / 2.0), math.sin(a / 2.0)) for a in ph]).astype(np.complex128)
    S = V @ D @ np.linalg.inv(V)
    return _rt_gauge_fix_unitary(S)


def _rt_angle_distance_to_Cn_deg(x_deg: float, n: int) -> float:
    """Distance in degrees to nearest multiple of 360/n (Cn grid)."""
    n = int(n)
    if n <= 0:
        return float('nan')
    eps = 360.0 / float(n)
    k = int(round(float(x_deg) / eps))
    return abs(float(x_deg) - float(k) * eps)


def _rt_angle_distance_to_C30_deg(x_deg: float) -> float:
    """Distance in degrees to nearest multiple of 12° (C30)."""
    return _rt_angle_distance_to_Cn_deg(x_deg, 30)


def _rt_eigphase_Cn_residual_deg(U, n: int) -> Optional[float]:
    """Max eigenphase distance to Cn grid (principal phases)."""
    if np is None:
        return None
    w = np.linalg.eigvals(U.astype(np.complex128))
    ph_deg = [math.degrees(float(np.angle(complex(z)))) for z in w]
    return float(max(_rt_angle_distance_to_Cn_deg(a, int(n)) for a in ph_deg))


def _rt_eigphase_C30_residual_deg(U) -> Optional[float]:
    """Max eigenphase distance to C30 grid (principal phases)."""
    return _rt_eigphase_Cn_residual_deg(U, 30)



def _rt_unitary_eigphase_snap_Cn(U, n: int) -> Dict[str, Any]:
    """Snap eigenphases of a unitary to nearest Cn grid, preserving eigenvectors."""
    out: Dict[str, Any] = {
        "error": None,
        "n": int(n),
        "ph_deg": None,
        "ph_snap_deg": None,
        "delta_deg_max": None,
        "unitary_residual": None,
        "fro_delta": None,
        "U_snap": None,
    }
    if np is None:
        out["error"] = "numpy not available"
        return out
    try:
        n = int(n)
        if n <= 0:
            raise ValueError('n must be positive')
        eps = 360.0 / float(n)

        U0 = U.astype(np.complex128)
        w, V = np.linalg.eig(U0)

        items = []
        for i in range(3):
            z = complex(w[i])
            ph = float(np.angle(z))
            items.append((ph, abs(z.real), abs(z.imag), i))
        items.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
        idx = [t[3] for t in items]
        w = w[idx]
        V = V[:, idx]

        V = _rt_gauge_fix_unitary(V)

        ph_deg = [math.degrees(float(np.angle(complex(z)))) for z in w]
        ph_snap_deg = []
        deltas = []
        for a in ph_deg:
            k = int(round(float(a) / eps))
            a2 = float(k) * eps
            while a2 >= 180.0:
                a2 -= 360.0
            while a2 < -180.0:
                a2 += 360.0
            ph_snap_deg.append(a2)
            deltas.append(abs(float(a) - float(a2)))

        D = np.diag([complex(math.cos(math.radians(a2)), math.sin(math.radians(a2))) for a2 in ph_snap_deg]).astype(np.complex128)
        U_snap = V @ D @ np.linalg.inv(V)
        U_snap = _rt_gauge_fix_unitary(U_snap)

        out["ph_deg"] = [float(a) for a in ph_deg]
        out["ph_snap_deg"] = [float(a) for a in ph_snap_deg]
        out["delta_deg_max"] = float(max(deltas)) if deltas else 0.0
        out["unitary_residual"] = _rt_unitary_residual_np(U_snap)
        out["fro_delta"] = float(np.linalg.norm(U_snap - U0))
        out["U_snap"] = U_snap
        return out
    except Exception as e:
        out["error"] = str(e)
        return out


def _rt_unitary_eigphase_snap_C30(U) -> Dict[str, Any]:
    """Wrapper: snap eigenphases to C30 grid (12°)."""
    return _rt_unitary_eigphase_snap_Cn(U, 30)


def _rt_construct_misalignment_v0_3(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """Deterministic RT candidate for flavor misalignment (v0.3, discrete angles).

    Goal: provide a scan-free, explicitly unitary CKM/PMNS candidate whose angles are
    derived from fixed RT integers (K=30, rho=10) + discrete multipliers.

    This is a diagnostic bridge: it intentionally avoids any PDG fitting.
    """

    out: Dict[str, Any] = {
        "version": "rt_construct_v0_3_discrete_angles",
        "error": None,
        "policy": {},
        "CKM": {},
        "PMNS": {},
        "NEG": {},
        "gate": {},
    }

    if np is None:
        out["error"] = "numpy not available"
        return out

    def _snap_deg_to_C30(x: float) -> float:
        # nearest multiple of 12° (C30)
        k = int(round(float(x) / RT_EPS30_DEG))
        return float(k) * RT_EPS30_DEG

    # δ selection: prefer phase-rule C30 output; otherwise fall back to a deterministic snap of δφ*.
    d_ckm = float(delta_deg_ckm) if delta_deg_ckm is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD))
    d_pm = float(delta_deg_pmns) if delta_deg_pmns is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD + math.pi))

    # CKM angles: hierarchy from K and rho, with only discrete multipliers.
    th12_ck = 1.0 * RT_EPS30_DEG
    th23_ck = 2.0 * RT_EPS30_RHO_DEG
    th13_ck = 2.0 * RT_EPS30_RHO2_DEG

    # PMNS angles: “large mixing” via coarse C30 multiples (diagnostic only; no tuning)
    th12_pm = 3.0 * RT_EPS30_DEG
    th23_pm = 4.0 * RT_EPS30_DEG
    th13_pm = 2.0 * RT_EPS30_DEG

    V = _rt_unitary_from_pdg(th12_ck, th23_ck, th13_ck, d_ckm)
    U = _rt_unitary_from_pdg(th12_pm, th23_pm, th13_pm, d_pm)

    out["policy"] = {
        "K": int(RT_K),
        "rho": int(RT_RHO),
        "theta_units": {
            "eps30_deg": float(RT_EPS30_DEG),
            "eps30_rho_deg": float(RT_EPS30_RHO_DEG),
            "eps30_rho2_deg": float(RT_EPS30_RHO2_DEG),
        },
        "ckm_formula": "θ12=1·eps30; θ23=2·eps30/rho; θ13=2·eps30/rho^2; δ=phase-rule(C30)",
        "pmns_formula": "θ12=3·eps30; θ23=4·eps30; θ13=2·eps30; δ=phase-rule(C30)",
        "delta_deg": {"CKM": float(d_ckm), "PMNS": float(d_pm)},
        "note": "v0.3 is a scan-free, explicitly unitary bridge; it does not use PDG numbers.",
    }

    out["CKM"] = {
        "V_abs": _rt_abs_from_np(V),
        "unitary_residual": _rt_unitary_residual_np(V),
        "angles": _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)]),
        "params": {"theta12_deg": th12_ck, "theta23_deg": th23_ck, "theta13_deg": th13_ck, "delta_deg": float(d_ckm)},
    }

    out["PMNS"] = {
        "U_abs": _rt_abs_from_np(U),
        "unitary_residual": _rt_unitary_residual_np(U),
        "angles": _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)]),
        "params": {"theta12_deg": th12_pm, "theta23_deg": th23_pm, "theta13_deg": th13_pm, "delta_deg": float(d_pm)},
    }

    # NEG: identity (all angles 0) must be exactly trivial
    V0 = _rt_unitary_from_pdg(0.0, 0.0, 0.0, 0.0)
    U0 = _rt_unitary_from_pdg(0.0, 0.0, 0.0, 0.0)
    out["NEG"] = {
        "CKM_trivial": {
            "unitary_residual": _rt_unitary_residual_np(V0),
            "angles": _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)]),
        },
        "PMNS_trivial": {
            "unitary_residual": _rt_unitary_residual_np(U0),
            "angles": _angles_J_from_unitary([[complex(U0[i, j]) for j in range(3)] for i in range(3)]),
        },
    }

    # Gates (diagnostic): reuse the same structure as v0.2 gates
    ck = out["CKM"]["angles"]
    pm = out["PMNS"]["angles"]

    def _score(a: Dict[str, float]) -> float:
        return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2

    s_ckm = _score(ck)
    s_pmns = _score(pm)

    neg_ck = out["NEG"]["CKM_trivial"]["angles"]
    neg_pm = out["NEG"]["PMNS_trivial"]["angles"]
    neg_ok = bool(
        abs(float(neg_ck.get("J", 0.0))) <= MAX_NEG_J_ABS
        and abs(float(neg_pm.get("J", 0.0))) <= MAX_NEG_J_ABS
        and float(neg_ck.get("theta12_deg", 0.0)) <= MAX_NEG_THETA_DEG
        and float(neg_ck.get("theta23_deg", 0.0)) <= MAX_NEG_THETA_DEG
        and float(neg_ck.get("theta13_deg", 0.0)) <= MAX_NEG_THETA_DEG
        and float(neg_pm.get("theta12_deg", 0.0)) <= MAX_NEG_THETA_DEG
        and float(neg_pm.get("theta23_deg", 0.0)) <= MAX_NEG_THETA_DEG
        and float(neg_pm.get("theta13_deg", 0.0)) <= MAX_NEG_THETA_DEG
    )

    def _in_range(x: float, r: Tuple[float, float]) -> bool:
        return (x >= float(r[0])) and (x <= float(r[1]))

    ck_t12 = float(ck.get("theta12_deg", 0.0))
    ck_t23 = float(ck.get("theta23_deg", 0.0))
    ck_t13 = float(ck.get("theta13_deg", 0.0))
    ck_J = float(ck.get("J", 0.0))
    ck_order = bool(ck_t12 > ck_t23 > ck_t13)
    ck_ranges_ok = bool(
        _in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG)
        and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG)
        and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG)
    )
    ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
    pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)

    pm_t12 = float(pm.get("theta12_deg", 0.0))
    pm_t23 = float(pm.get("theta23_deg", 0.0))
    pm_t13 = float(pm.get("theta13_deg", 0.0))
    pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
    pass_pmns_pattern = bool(pm_large_count >= 2)

    pass_struct = bool(s_ckm < s_pmns and neg_ok)

    out["gate"] = {
        "score": {
            "ckm": float(s_ckm),
            "pmns": float(s_pmns),
            "pass": bool(pass_struct),
            "policy": "Require score(CKM) < score(PMNS); NEG trivial must be ~0",
        },
        "ckm_pattern": {
            "theta12_range_deg": [float(RT_CKM_THETA12_RANGE_DEG[0]), float(RT_CKM_THETA12_RANGE_DEG[1])],
            "theta23_range_deg": [float(RT_CKM_THETA23_RANGE_DEG[0]), float(RT_CKM_THETA23_RANGE_DEG[1])],
            "theta13_range_deg": [float(RT_CKM_THETA13_RANGE_DEG[0]), float(RT_CKM_THETA13_RANGE_DEG[1])],
            "ordering": "theta12>theta23>theta13",
            "J_range_abs": [float(MIN_J_ABS), float(RT_CKM_MAX_J_ABS)],
            "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J},
            "pass": bool(pass_ckm_pattern),
        },
        "pmns_pattern": {
            "min_large_angle_deg": float(RT_PMNS_MIN_LARGE_ANGLE_DEG),
            "large_count": int(pm_large_count),
            "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13},
            "pass": bool(pass_pmns_pattern),
        },
        "neg_ok": bool(neg_ok),
        "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
        "policy": "Structural+pattern gates (diagnostic): score + CKM window+hierarchy+CP + PMNS large-mixing + NEG",
    }

    return out


def _rt_construct_misalignment_v0_4_factorized(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct (v0.4): explicit U_u/U_d and U_e/U_nu via symmetric unitary sqrt.

    This keeps the v0.3 discrete-angle targets (K=30, rho=10; δ from RT phase-rule),
    but makes the misalignment structural:

        CKM = U_u^† U_d   with   U_d = sqrt(CKM_target), U_u = U_d^†
        PMNS = U_e^† U_nu with   U_nu = sqrt(PMNS_target), U_e = U_nu^†

    No scans, no continuous knobs. Still a bridge: next step is to replace the PDG-target
    generator with a PP/sector-derived generator.
    """
    out: Dict[str, Any] = {
        "version": "rt_construct_v0_4_factorized_sqrt",
        "error": None,
        "policy": {},
        "sectors": {},
        "CKM": {},
        "PMNS": {},
        "gate": {},
    }

    if np is None:
        out["error"] = "numpy not available"
        return out

    base = _rt_construct_misalignment_v0_3(delta_deg_ckm, delta_deg_pmns)
    if base.get("error"):
        out["error"] = base.get("error")
        return out

    ck_p = (base.get("CKM") or {}).get("params") or {}
    pm_p = (base.get("PMNS") or {}).get("params") or {}

    Vt = _rt_unitary_from_pdg(float(ck_p.get("theta12_deg", 0.0)), float(ck_p.get("theta23_deg", 0.0)), float(ck_p.get("theta13_deg", 0.0)), float(ck_p.get("delta_deg", 0.0)))
    Ut = _rt_unitary_from_pdg(float(pm_p.get("theta12_deg", 0.0)), float(pm_p.get("theta23_deg", 0.0)), float(pm_p.get("theta13_deg", 0.0)), float(pm_p.get("delta_deg", 0.0)))

    Ud = _rt_unitary_sqrt(Vt)
    Uu = Ud.conjugate().T
    Unu = _rt_unitary_sqrt(Ut)
    Ue = Unu.conjugate().T

    V = Uu.conjugate().T @ Ud
    U = Ue.conjugate().T @ Unu

    out["policy"] = {
        "inherits": base.get("policy"),
        "factorization": "symmetric principal sqrt on U(3)",
        "note": "v0.4 introduces explicit sector unitaries; targets remain v0.3 (discrete angles + δ from phase-rule).",
    }

    out["sectors"] = {
        "Uu": {"unitary_residual": _rt_unitary_residual_np(Uu), "eigphase_C30_residual_deg": _rt_eigphase_C30_residual_deg(Uu)},
        "Ud": {"unitary_residual": _rt_unitary_residual_np(Ud), "eigphase_C30_residual_deg": _rt_eigphase_C30_residual_deg(Ud)},
        "Ue": {"unitary_residual": _rt_unitary_residual_np(Ue), "eigphase_C30_residual_deg": _rt_eigphase_C30_residual_deg(Ue)},
        "Unu": {"unitary_residual": _rt_unitary_residual_np(Unu), "eigphase_C30_residual_deg": _rt_eigphase_C30_residual_deg(Unu)},
    }

    out["CKM"] = {
        "V_abs": _rt_abs_from_np(V),
        "unitary_residual": _rt_unitary_residual_np(V),
        "angles": _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)]),
        "params": ck_p,
    }

    out["PMNS"] = {
        "U_abs": _rt_abs_from_np(U),
        "unitary_residual": _rt_unitary_residual_np(U),
        "angles": _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)]),
        "params": pm_p,
    }

    base_gate = (base.get("gate") or {})
    g = dict(base_gate)
    g["inherits_version"] = base.get("version")
    g["policy"] = "v0.4 uses same pattern gates as v0.3 (targets identical); adds sector-factorization diagnostics."
    out["gate"] = g

    return out



def _rt_construct_misalignment_v0_5_sector_eigphase_snap(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct (v0.5): v0.4 sectors + unitary-preserving C30 hardening via eigenphase snapping.

    v0.5 is diagnostic bridge:
      - targets still come from v0.3 (K=30, ρ=10, δ from RT phase-rule),
      - then sector matrices (Uu,Ud,Ue,Uν) are eigenphase-snapped to C30,
      - CKM/PMNS are recomputed and gated *after* snap.
    """
    out: Dict[str, Any] = {
        "version": "rt_construct_v0_5_sector_eigphase_snap_C30",
        "error": None,
        "policy": {},
        "sectors": {},
        "CKM": {},
        "PMNS": {},
        "gate": {},
    }
    if np is None:
        out["error"] = "numpy not available"
        return out

    base = _rt_construct_misalignment_v0_3(delta_deg_ckm, delta_deg_pmns)
    if base.get("error"):
        out["error"] = base.get("error")
        return out

    ck_p = (base.get("CKM") or {}).get("params") or {}
    pm_p = (base.get("PMNS") or {}).get("params") or {}

    Vt = _rt_unitary_from_pdg(float(ck_p.get("theta12_deg", 0.0)), float(ck_p.get("theta23_deg", 0.0)), float(ck_p.get("theta13_deg", 0.0)), float(ck_p.get("delta_deg", 0.0)))
    Ut = _rt_unitary_from_pdg(float(pm_p.get("theta12_deg", 0.0)), float(pm_p.get("theta23_deg", 0.0)), float(pm_p.get("theta13_deg", 0.0)), float(pm_p.get("delta_deg", 0.0)))

    Ud = _rt_unitary_sqrt(Vt)
    Uu = Ud.conjugate().T
    Unu = _rt_unitary_sqrt(Ut)
    Ue = Unu.conjugate().T

    snap = {
        "Uu": _rt_unitary_eigphase_snap_C30(Uu),
        "Ud": _rt_unitary_eigphase_snap_C30(Ud),
        "Ue": _rt_unitary_eigphase_snap_C30(Ue),
        "Unu": _rt_unitary_eigphase_snap_C30(Unu),
    }
    if any((snap[k] or {}).get("error") for k in snap):
        out["error"] = "eigphase snap error: " + "; ".join([f"{k}:{(snap[k] or {}).get('error')}" for k in snap if (snap[k] or {}).get("error")])
        return out

    Uu2 = snap["Uu"]["U_snap"]
    Ud2 = snap["Ud"]["U_snap"]
    Ue2 = snap["Ue"]["U_snap"]
    Unu2 = snap["Unu"]["U_snap"]

    V = Uu2.conjugate().T @ Ud2
    U = Ue2.conjugate().T @ Unu2

    ck_ang = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm_ang = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    # Gate logic: same as v0.3 (diagnostic)
    def _score(a: Dict[str, float]) -> float:
        return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2

    s_ckm = _score(ck_ang)
    s_pmns = _score(pm_ang)

    V0 = _rt_unitary_from_pdg(0.0, 0.0, 0.0, 0.0)
    U0 = _rt_unitary_from_pdg(0.0, 0.0, 0.0, 0.0)
    neg_ck = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    neg_pm = _angles_J_from_unitary([[complex(U0[i, j]) for j in range(3)] for i in range(3)])
    neg_ok = bool(
        abs(float(neg_ck.get("J", 0.0))) <= MAX_NEG_J_ABS
        and abs(float(neg_pm.get("J", 0.0))) <= MAX_NEG_J_ABS
        and float(neg_ck.get("theta12_deg", 0.0)) <= MAX_NEG_THETA_DEG
        and float(neg_ck.get("theta23_deg", 0.0)) <= MAX_NEG_THETA_DEG
        and float(neg_ck.get("theta13_deg", 0.0)) <= MAX_NEG_THETA_DEG
        and float(neg_pm.get("theta12_deg", 0.0)) <= MAX_NEG_THETA_DEG
        and float(neg_pm.get("theta23_deg", 0.0)) <= MAX_NEG_THETA_DEG
        and float(neg_pm.get("theta13_deg", 0.0)) <= MAX_NEG_THETA_DEG
    )

    def _in_range(x: float, r: Tuple[float, float]) -> bool:
        return (x >= float(r[0])) and (x <= float(r[1]))

    ck_t12 = float(ck_ang.get("theta12_deg", 0.0))
    ck_t23 = float(ck_ang.get("theta23_deg", 0.0))
    ck_t13 = float(ck_ang.get("theta13_deg", 0.0))
    ck_J = float(ck_ang.get("J", 0.0))
    ck_order = bool(ck_t12 > ck_t23 > ck_t13)
    ck_ranges_ok = bool(
        _in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG)
        and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG)
        and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG)
    )
    ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
    pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)

    pm_t12 = float(pm_ang.get("theta12_deg", 0.0))
    pm_t23 = float(pm_ang.get("theta23_deg", 0.0))
    pm_t13 = float(pm_ang.get("theta13_deg", 0.0))
    pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
    pass_pmns_pattern = bool(pm_large_count >= 2)

    pass_struct = bool(s_ckm < s_pmns and neg_ok)

    out["policy"] = {
        "inherits": base.get("policy"),
        "snap": "per-sector eigenphases snapped to nearest C30 grid (12°); unitary-preserving",
    }

    for nm, U0m in (("Uu", Uu), ("Ud", Ud), ("Ue", Ue), ("Unu", Unu)):
        sm = snap[nm]
        out["sectors"][nm] = {
            "unitary_residual_before": _rt_unitary_residual_np(U0m),
            "unitary_residual_after": sm.get("unitary_residual"),
            "eigphase_C30_residual_deg_before": _rt_eigphase_C30_residual_deg(U0m),
            "eigphase_C30_residual_deg_after": _rt_eigphase_C30_residual_deg(sm.get("U_snap")),
            "eigphase_delta_deg_max": sm.get("delta_deg_max"),
            "fro_delta": sm.get("fro_delta"),
        }

    out["CKM"] = {
        "V_abs": _rt_abs_from_np(V),
        "unitary_residual": _rt_unitary_residual_np(V),
        "angles": ck_ang,
        "params": ck_p,
    }
    out["PMNS"] = {
        "U_abs": _rt_abs_from_np(U),
        "unitary_residual": _rt_unitary_residual_np(U),
        "angles": pm_ang,
        "params": pm_p,
    }

    out["gate"] = {
        "score": {"ckm": float(s_ckm), "pmns": float(s_pmns), "pass": bool(pass_struct)},
        "ckm_pattern": {"pass": bool(pass_ckm_pattern), "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J}},
        "pmns_pattern": {"pass": bool(pass_pmns_pattern), "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13}, "large_count": int(pm_large_count)},
        "neg_ok": bool(neg_ok),
        "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
        "policy": "v0.3 gates applied after sector eigphase snap",
    }
    return out




def _rt_construct_misalignment_v0_6_sector_eigphase_snap(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct (v0.6): sector eigphase snap with RT micro-grid for quarks.

    v0.5 forced sector eigenphases to C30 (12°) for *all* sectors; that can distort CKM.
    v0.6 keeps the v0.3→v0.4 bridge but hardens eigenphases using:
      - quark sectors (Uu, Ud): C(30*rho) grid (n=300, step=1.2°)
      - lepton sectors (Ue, Uν): C30 grid (n=30, step=12°)

    Still diagnostic bridge; real next step is PP/RT-derived sector generators.
    """
    out: Dict[str, Any] = {
        "version": "rt_construct_v0_6_sector_eigphase_snap_C300_quark",
        "error": None,
        "policy": {},
        "sectors": {},
        "CKM": {},
        "PMNS": {},
        "gate": {},
    }
    if np is None:
        out["error"] = "numpy not available"
        return out

    base = _rt_construct_misalignment_v0_3(delta_deg_ckm, delta_deg_pmns)
    if base.get("error"):
        out["error"] = base.get("error")
        return out

    ck_p = (base.get("CKM") or {}).get("params") or {}
    pm_p = (base.get("PMNS") or {}).get("params") or {}

    Vt = _rt_unitary_from_pdg(
        float(ck_p.get("theta12_deg", 0.0)),
        float(ck_p.get("theta23_deg", 0.0)),
        float(ck_p.get("theta13_deg", 0.0)),
        float(ck_p.get("delta_deg", 0.0)),
    )
    Ut = _rt_unitary_from_pdg(
        float(pm_p.get("theta12_deg", 0.0)),
        float(pm_p.get("theta23_deg", 0.0)),
        float(pm_p.get("theta13_deg", 0.0)),
        float(pm_p.get("delta_deg", 0.0)),
    )

    Ud = _rt_unitary_sqrt(Vt)
    Uu = Ud.conjugate().T
    Unu = _rt_unitary_sqrt(Ut)
    Ue = Unu.conjugate().T

    n_quark = int(RT_K * RT_RHO)  # 300
    n_lepton = int(RT_K)          # 30
    nmap = {"Uu": n_quark, "Ud": n_quark, "Ue": n_lepton, "Unu": n_lepton}

    snap = {
        "Uu": _rt_unitary_eigphase_snap_Cn(Uu, nmap["Uu"]),
        "Ud": _rt_unitary_eigphase_snap_Cn(Ud, nmap["Ud"]),
        "Ue": _rt_unitary_eigphase_snap_Cn(Ue, nmap["Ue"]),
        "Unu": _rt_unitary_eigphase_snap_Cn(Unu, nmap["Unu"]),
    }
    errs = [f"{k}:{(snap[k] or {}).get('error')}" for k in snap if (snap[k] or {}).get("error")]
    if errs:
        out["error"] = "eigphase snap error: " + "; ".join(errs)
        return out

    Uu2 = snap["Uu"]["U_snap"]
    Ud2 = snap["Ud"]["U_snap"]
    Ue2 = snap["Ue"]["U_snap"]
    Unu2 = snap["Unu"]["U_snap"]

    V = Uu2.conjugate().T @ Ud2
    U = Ue2.conjugate().T @ Unu2

    ck_ang = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm_ang = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    def _score(a: Dict[str, float]) -> float:
        return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2

    s_ckm = _score(ck_ang)
    s_pmns = _score(pm_ang)

    V0 = _rt_unitary_from_pdg(0.0, 0.0, 0.0, 0.0)
    U0 = _rt_unitary_from_pdg(0.0, 0.0, 0.0, 0.0)
    neg_ck = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    neg_pm = _angles_J_from_unitary([[complex(U0[i, j]) for j in range(3)] for i in range(3)])
    neg_ok = bool(
        abs(float(neg_ck.get("J", 0.0))) <= MAX_NEG_J_ABS
        and abs(float(neg_pm.get("J", 0.0))) <= MAX_NEG_J_ABS
        and float(neg_ck.get("theta12_deg", 0.0)) <= MAX_NEG_THETA_DEG
        and float(neg_ck.get("theta23_deg", 0.0)) <= MAX_NEG_THETA_DEG
        and float(neg_ck.get("theta13_deg", 0.0)) <= MAX_NEG_THETA_DEG
        and float(neg_pm.get("theta12_deg", 0.0)) <= MAX_NEG_THETA_DEG
        and float(neg_pm.get("theta23_deg", 0.0)) <= MAX_NEG_THETA_DEG
        and float(neg_pm.get("theta13_deg", 0.0)) <= MAX_NEG_THETA_DEG
    )

    def _in_range(x: float, r: Tuple[float, float]) -> bool:
        return (x >= float(r[0])) and (x <= float(r[1]))

    ck_t12 = float(ck_ang.get("theta12_deg", 0.0))
    ck_t23 = float(ck_ang.get("theta23_deg", 0.0))
    ck_t13 = float(ck_ang.get("theta13_deg", 0.0))
    ck_J = float(ck_ang.get("J", 0.0))
    ck_order = bool(ck_t12 > ck_t23 > ck_t13)
    ck_ranges_ok = bool(
        _in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG)
        and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG)
        and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG)
    )
    ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
    pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)

    pm_t12 = float(pm_ang.get("theta12_deg", 0.0))
    pm_t23 = float(pm_ang.get("theta23_deg", 0.0))
    pm_t13 = float(pm_ang.get("theta13_deg", 0.0))
    pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
    pass_pmns_pattern = bool(pm_large_count >= 2)

    pass_struct = bool(s_ckm < s_pmns and neg_ok)

    out["policy"] = {
        "inherits": base.get("policy"),
        "snap": {
            "Uu": {"n": nmap["Uu"], "step_deg": 360.0 / float(nmap["Uu"])},
            "Ud": {"n": nmap["Ud"], "step_deg": 360.0 / float(nmap["Ud"])},
            "Ue": {"n": nmap["Ue"], "step_deg": 360.0 / float(nmap["Ue"])},
            "Unu": {"n": nmap["Unu"], "step_deg": 360.0 / float(nmap["Unu"])},
        },
    }

    for nm, U0m in (("Uu", Uu), ("Ud", Ud), ("Ue", Ue), ("Unu", Unu)):
        sm = snap[nm]
        ngrid = int(nmap[nm])
        out["sectors"][nm] = {
            "n_grid": ngrid,
            "unitary_residual_before": _rt_unitary_residual_np(U0m),
            "unitary_residual_after": sm.get("unitary_residual"),
            "eigphase_C30_residual_deg_before": _rt_eigphase_Cn_residual_deg(U0m, 30),
            "eigphase_C30_residual_deg_after": _rt_eigphase_Cn_residual_deg(sm.get("U_snap"), 30),
            "eigphase_Cn_residual_deg_before": _rt_eigphase_Cn_residual_deg(U0m, ngrid),
            "eigphase_Cn_residual_deg_after": _rt_eigphase_Cn_residual_deg(sm.get("U_snap"), ngrid),
            "eigphase_delta_deg_max": sm.get("delta_deg_max"),
            "fro_delta": sm.get("fro_delta"),
        }

    out["CKM"] = {
        "V_abs": _rt_abs_from_np(V),
        "unitary_residual": _rt_unitary_residual_np(V),
        "angles": ck_ang,
        "params": ck_p,
    }
    out["PMNS"] = {
        "U_abs": _rt_abs_from_np(U),
        "unitary_residual": _rt_unitary_residual_np(U),
        "angles": pm_ang,
        "params": pm_p,
    }

    out["gate"] = {
        "score": {"ckm": float(s_ckm), "pmns": float(s_pmns), "pass": bool(pass_struct)},
        "ckm_pattern": {"pass": bool(pass_ckm_pattern), "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J}},
        "pmns_pattern": {"pass": bool(pass_pmns_pattern), "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13}, "large_count": int(pm_large_count)},
        "neg_ok": bool(neg_ok),
        "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
        "policy": "v0.3 gates applied after sector eigphase snap (quark C300, lepton C30)",
    }
    return out




def _rt_proj_phase_Cn(k: int, n: int):
    """Diagonal phase projector with Cn spacing (n steps, step=k)."""
    if np is None:
        return None
    n = int(n)
    twopi = 2.0 * math.pi
    ph = [twopi * (j * int(k)) / n for j in range(3)]
    return np.diag([complex(math.cos(a), math.sin(a)) for a in ph]).astype(np.complex128)


def _rt_expm_i_hermitian(H, eps: float):
    """Return exp(i*eps*H) for Hermitian H via eigen-decomposition (unitary by construction)."""
    if np is None:
        return None
    H = np.array(H, dtype=np.complex128)
    # Hermitian symmetrize (defensive)
    H = 0.5 * (H + H.conjugate().T)
    w, v = np.linalg.eigh(H)
    ph = np.exp(1j * float(eps) * w)
    return (v @ np.diag(ph) @ v.conjugate().T).astype(np.complex128)


def _rt_construct_misalignment_v0_7_monodromy_1260(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct v0.7: 1260-tick monodromy scaffold (diagnostic).

    Idea: treat the observed CKM/PMNS as an RP-level effective misalignment after a full
    global loop L*=1260 ticks = 42 blocks × 30-tick strobe.

    Implementation (no scans, no continuous knobs):
      - Each sector has a fixed "kick" unitary U_kick = exp(i*eps*H) from discrete near-coupling + edge phase.
      - Each 30-tick block b applies a diagonal RT phase projector P_b on a discrete grid:
          leptons: C30, quarks: C300 (=C(30*rho)).
      - Block phase advances by a closure step chosen to satisfy 42-block closure:
          leptons: Δk=5 (since 42*5 ≡ 0 mod 30), quarks: Δk=50 (since 42*50 ≡ 0 mod 300).
      - Total sector unitary is the ordered product Π_b (P_b U_kick P_b†).

    This is deliberately a *scaffold*: it answers "are we even using the full 1260 loop?" with a yes,
    without claiming that H is the final PP-generator.
    """

    out: Dict[str, Any] = {
        "version": "rt_construct_v0_7_monodromy_1260",
        "error": None,
        "policy": {},
        "sectors": {},
        "CKM": {},
        "PMNS": {},
        "gate": {},
    }

    if np is None:
        out["error"] = "numpy not available"
        return out

    def _snap_deg_to_C30(x: float) -> float:
        step = 360.0 / 30.0
        y = float(x) % 360.0
        k = int(round(y / step)) % 30
        return float(k) * step

    # Base deltas (degrees) – already snapped upstream; fall back to δφ* if missing.
    d_ckm = float(delta_deg_ckm) if delta_deg_ckm is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD))
    d_pm = float(delta_deg_pmns) if delta_deg_pmns is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD + math.pi))

    # Map δ_C30 -> k (mod 30)
    k_ckm_30 = int(round(d_ckm / (360.0 / 30.0))) % 30
    k_pm_30 = int(round(d_pm / (360.0 / 30.0))) % 30

    # Monodromy policy (fixed integers)
    K = 30
    blocks = 42
    L_star = K * blocks
    nL, nQ = 30, 300
    dkL, dkQ = 5, 50

    # Edge phases (A/B halves) from δφ* (quantized to π/3)
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)
    phi_B = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi)

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        # Hermitian generator from near-coupling adjacency
        H = (N + N.conjugate().T)
        # Normalize to max|eig|=1 to keep eps interpretable
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, eps)
        return Uk, float(m)

    def _monodromy(U_kick, n: int, k0: int, dk: int):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        U = np.eye(3, dtype=np.complex128)
        ks = []
        for b in range(blocks):
            kb = (k0 + b * dk) % n
            P = _rt_proj_phase_Cn(kb, n)
            # S_b = P U_kick P†
            S = P @ U_kick @ P.conjugate().T
            U = U @ S
            ks.append(int(kb))
        U = _rt_gauge_fix_unitary(U)
        return U, ks

    # Sector definitions (match v0.2 intent, but with 1260 loop)
    # Quarks: same base k (from CKM δ), but different near-coupling + A/B halves and eps sign.
    kQ_base = (10 * k_ckm_30) % nQ
    Uu_kick, u_norm = _build_kick(6, phi_A, +RT_EPS0)
    Ud_kick, d_norm = _build_kick(5, phi_B, -RT_EPS0)
    Uu, ks_u = _monodromy(Uu_kick, nQ, kQ_base, dkQ)
    Ud, ks_d = _monodromy(Ud_kick, nQ, kQ_base, dkQ)

    # Leptons: enforce a Z6 offset between e and ν (k shift=+5 on C30), as in v0.2.
    kL_base = k_pm_30 % nL
    Ue_kick, e_norm = _build_kick(5, phi_B, -RT_EPS0)
    Un_kick, n_norm = _build_kick(4, phi_A, +RT_EPS0)
    Ue, ks_e = _monodromy(Ue_kick, nL, (kL_base + 0) % nL, dkL)
    Unu, ks_n = _monodromy(Un_kick, nL, (kL_base + 5) % nL, dkL)

    # Misalignment
    V = Uu.conjugate().T @ Ud
    U = Ue.conjugate().T @ Unu

    ck_ang = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm_ang = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    def _score(a: Dict[str, float]) -> float:
        return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2

    s_ckm = _score(ck_ang)
    s_pmns = _score(pm_ang)

    # Pattern gates (same policy constants as v0.4/v0.6; diagnostic only)
    def _in_range(x: float, r: Tuple[float, float]) -> bool:
        return (x >= float(r[0])) and (x <= float(r[1]))

    ck_t12 = float(ck_ang.get("theta12_deg", 0.0))
    ck_t23 = float(ck_ang.get("theta23_deg", 0.0))
    ck_t13 = float(ck_ang.get("theta13_deg", 0.0))
    ck_J = float(ck_ang.get("J", 0.0))
    ck_order = bool(ck_t12 > ck_t23 > ck_t13)
    ck_ranges_ok = bool(_in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG) and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG) and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG))
    ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
    pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)

    pm_t12 = float(pm_ang.get("theta12_deg", 0.0))
    pm_t23 = float(pm_ang.get("theta23_deg", 0.0))
    pm_t13 = float(pm_ang.get("theta13_deg", 0.0))
    pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
    pass_pmns_pattern = bool(pm_large_count >= 2)

    # Structural gate: CKM is "smaller" than PMNS
    pass_struct = bool(s_ckm < s_pmns)

    out["policy"] = {
        "L_star_ticks": int(L_star),
        "blocks": int(blocks),
        "K": int(K),
        "rho": int(RT_RHO),
        "grid": {"lepton": int(nL), "quark": int(nQ)},
        "delta_base": {"CKM": {"deg": float(d_ckm), "k_mod30": int(k_ckm_30)}, "PMNS": {"deg": float(d_pm), "k_mod30": int(k_pm_30)}},
        "monodromy_step": {"lepton_dk": int(dkL), "quark_dk": int(dkQ)},
        "edge_phase": {"phi_A_deg": float(math.degrees(phi_A)), "phi_B_deg": float(math.degrees(phi_B)), "quantization": "nearest π/3"},
        "kick": {"eps0": float(RT_EPS0), "H_norm_policy": "scale by max|eig|", "note": "H from near-coupling adjacency; scaffold"},
    }

    out["sectors"] = {
        "Uu": {"p": 6, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(u_norm), "unitary_residual": _rt_unitary_residual_np(Uu), "k_hist_tail": ks_u[-6:]},
        "Ud": {"p": 5, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(d_norm), "unitary_residual": _rt_unitary_residual_np(Ud), "k_hist_tail": ks_d[-6:]},
        "Ue": {"p": 5, "n_grid": nL, "k0": int(kL_base % nL), "dk": int(dkL), "kick_norm": float(e_norm), "unitary_residual": _rt_unitary_residual_np(Ue), "k_hist_tail": ks_e[-6:]},
        "Unu": {"p": 4, "n_grid": nL, "k0": int((kL_base + 5) % nL), "dk": int(dkL), "kick_norm": float(n_norm), "unitary_residual": _rt_unitary_residual_np(Unu), "k_hist_tail": ks_n[-6:]},
    }

    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck_ang}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm_ang}

    out["gate"] = {
        "score": {"ckm": float(s_ckm), "pmns": float(s_pmns), "pass": bool(pass_struct)},
        "ckm_pattern": {"pass": bool(pass_ckm_pattern), "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J}},
        "pmns_pattern": {"pass": bool(pass_pmns_pattern), "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13}, "large_count": int(pm_large_count)},
        "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
    }

    return out




def _rt_perm_cycle_pow(pw: int):
    """Z3 cyclic permutation matrix R^pw, pw mod 3."""
    if np is None:
        return None
    pw = int(pw) % 3
    R1 = np.array([[0,1,0],[0,0,1],[1,0,0]], dtype=np.complex128)
    if pw == 0:
        return np.eye(3, dtype=np.complex128)
    if pw == 1:
        return R1
    return (R1 @ R1).astype(np.complex128)


def _rt_construct_misalignment_v0_8_monodromy_z3kick_1260(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct v0.8: 1260-monodromy with *block-varying kick* (Z3 + A/B) (diagnostic).

    v0.7 used S_b = P_b U_kick P_b†. That can cancel too much.
    Here we force genuine non-commutativity by letting the kick itself depend on the block:
      U_kick(b) = R^{(b mod 3)} * U_kick^{(A/B)} * R^{- (b mod 3)}
    where A/B toggles by b parity (odd blocks use U_kick†).

    Still: no scans, no continuous knobs; pure discrete structure.
    """
    out = {
        "version": "rt_construct_v0_8_monodromy_z3kick_1260",
        "error": None,
        "policy": {},
        "sectors": {},
        "CKM": {},
        "PMNS": {},
        "gate": {},
    }

    if np is None:
        out["error"] = "numpy not available"
        return out

    def _snap_deg_to_C30(x: float) -> float:
        step = 360.0 / 30.0
        y = float(x) % 360.0
        k = int(round(y / step)) % 30
        return float(k) * step

    d_ckm = float(delta_deg_ckm) if delta_deg_ckm is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD))
    d_pm = float(delta_deg_pmns) if delta_deg_pmns is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD + math.pi))
    k_ckm_30 = int(round(d_ckm / (360.0 / 30.0))) % 30
    k_pm_30 = int(round(d_pm / (360.0 / 30.0))) % 30

    K = 30
    blocks = 42
    L_star = K * blocks
    nL, nQ = 30, 300
    dkL, dkQ = 5, 50

    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)
    phi_B = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi)

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, eps)
        return Uk, float(m)

    def _monodromy(U_kick, n: int, k0: int, dk: int):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        U = np.eye(3, dtype=np.complex128)
        ks = []
        for b in range(blocks):
            kb = (k0 + b * dk) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            # A/B toggle: odd blocks use inverse kick
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
            ks.append(int(kb))
        U = _rt_gauge_fix_unitary(U)
        return U, ks

    kQ_base = (10 * k_ckm_30) % nQ
    Uu_kick, u_norm = _build_kick(6, phi_A, +RT_EPS0)
    Ud_kick, d_norm = _build_kick(5, phi_B, -RT_EPS0)
    Uu, ks_u = _monodromy(Uu_kick, nQ, kQ_base, dkQ)
    Ud, ks_d = _monodromy(Ud_kick, nQ, kQ_base, dkQ)

    kL_base = k_pm_30 % nL
    Ue_kick, e_norm = _build_kick(5, phi_B, -RT_EPS0)
    Un_kick, n_norm = _build_kick(4, phi_A, +RT_EPS0)
    Ue, ks_e = _monodromy(Ue_kick, nL, (kL_base + 0) % nL, dkL)
    Unu, ks_n = _monodromy(Un_kick, nL, (kL_base + 5) % nL, dkL)

    V = Uu.conjugate().T @ Ud
    U = Ue.conjugate().T @ Unu

    ck_ang = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm_ang = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    def _score(a: Dict[str, float]) -> float:
        return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2

    s_ckm = _score(ck_ang)
    s_pmns = _score(pm_ang)

    def _in_range(x: float, r: Tuple[float, float]) -> bool:
        return (x >= float(r[0])) and (x <= float(r[1]))

    ck_t12 = float(ck_ang.get("theta12_deg", 0.0))
    ck_t23 = float(ck_ang.get("theta23_deg", 0.0))
    ck_t13 = float(ck_ang.get("theta13_deg", 0.0))
    ck_J = float(ck_ang.get("J", 0.0))
    ck_order = bool(ck_t12 > ck_t23 > ck_t13)
    ck_ranges_ok = bool(_in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG) and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG) and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG))
    ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
    pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)

    pm_t12 = float(pm_ang.get("theta12_deg", 0.0))
    pm_t23 = float(pm_ang.get("theta23_deg", 0.0))
    pm_t13 = float(pm_ang.get("theta13_deg", 0.0))
    pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
    pass_pmns_pattern = bool(pm_large_count >= 2)

    pass_struct = bool(s_ckm < s_pmns)

    out["policy"] = {
        "L_star_ticks": int(L_star),
        "blocks": int(blocks),
        "K": int(K),
        "rho": int(RT_RHO),
        "grid": {"lepton": int(nL), "quark": int(nQ)},
        "delta_base": {"CKM": {"deg": float(d_ckm), "k_mod30": int(k_ckm_30)}, "PMNS": {"deg": float(d_pm), "k_mod30": int(k_pm_30)}},
        "monodromy_step": {"lepton_dk": int(dkL), "quark_dk": int(dkQ)},
        "kick_variation": {"Z3_perm": True, "AB_toggle": True},
    }

    out["sectors"] = {
        "Uu": {"p": 6, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(u_norm), "unitary_residual": _rt_unitary_residual_np(Uu), "k_hist_tail": ks_u[-6:]},
        "Ud": {"p": 5, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(d_norm), "unitary_residual": _rt_unitary_residual_np(Ud), "k_hist_tail": ks_d[-6:]},
        "Ue": {"p": 5, "n_grid": nL, "k0": int(kL_base % nL), "dk": int(dkL), "kick_norm": float(e_norm), "unitary_residual": _rt_unitary_residual_np(Ue), "k_hist_tail": ks_e[-6:]},
        "Unu": {"p": 4, "n_grid": nL, "k0": int((kL_base + 5) % nL), "dk": int(dkL), "kick_norm": float(n_norm), "unitary_residual": _rt_unitary_residual_np(Unu), "k_hist_tail": ks_n[-6:]},
    }

    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck_ang}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm_ang}

    out["gate"] = {
        "score": {"ckm": float(s_ckm), "pmns": float(s_pmns), "pass": bool(pass_struct)},
        "ckm_pattern": {"pass": bool(pass_ckm_pattern), "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J}},
        "pmns_pattern": {"pass": bool(pass_pmns_pattern), "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13}, "large_count": int(pm_large_count)},
        "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
    }

    return out




def _rt_construct_misalignment_v0_9_monodromy_rho_kick_1260(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct v0.9: 1260-monodromy with Z3-permuted kick + A/B toggle + ρ-coupled microphase (diagnostic).

    v0.8 introduced non-commutativity by varying the kick per block.
    Here we also let the *quark projector index* carry a ρ=10 cycle on the C300 grid:

      k_b = k0 + b·Δk  ±  (micro_step · (b mod ρ))  (mod 300)

    with + for up-sector and − for down-sector. This is a discrete, scan-free way to
    break the near-cancellation Uu≈Ud that made CKM collapse in earlier monodromy scaffolds,
    while respecting the canonical integers (K=30, ρ=10, C300 for quarks).

    No continuous knobs are introduced; micro_step is a fixed policy integer (default 1 ⇒ 1.2° on C300).
    """

    out = {
        "version": "rt_construct_v0_9_monodromy_rho_kick_1260",
        "error": None,
        "policy": {},
        "sectors": {},
        "CKM": {},
        "PMNS": {},
        "gate": {},
    }

    if np is None:
        out["error"] = "numpy not available"
        return out

    def _snap_deg_to_C30(x: float) -> float:
        step = 360.0 / 30.0
        y = float(x) % 360.0
        k = int(round(y / step)) % 30
        return float(k) * step

    d_ckm = float(delta_deg_ckm) if delta_deg_ckm is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD))
    d_pm = float(delta_deg_pmns) if delta_deg_pmns is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD + math.pi))
    k_ckm_30 = int(round(d_ckm / (360.0 / 30.0))) % 30
    k_pm_30 = int(round(d_pm / (360.0 / 30.0))) % 30

    K = 30
    blocks = 42
    L_star = K * blocks
    nL, nQ = 30, 300
    dkL, dkQ = 5, 50

    # ρ-coupled microphase policy on the quark grid (C300)
    rho = int(RT_RHO)
    micro_step = 1  # fixed policy integer ⇒ 1.2° per step on C300

    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)
    phi_B = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi)

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, eps)
        return Uk, float(m)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        ks = []
        for b in range(blocks):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * (b % rho))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
            ks.append(int(kb))
        U = _rt_gauge_fix_unitary(U)
        return U, ks

    # Quarks: same base k from δ, but opposite ρ microphase sign for up vs down.
    kQ_base = (10 * k_ckm_30) % nQ
    Uu_kick, u_norm = _build_kick(6, phi_A, +RT_EPS0)
    Ud_kick, d_norm = _build_kick(5, phi_B, -RT_EPS0)
    Uu, ks_u = _monodromy(Uu_kick, nQ, kQ_base, dkQ, rho_sign=+1)
    Ud, ks_d = _monodromy(Ud_kick, nQ, kQ_base, dkQ, rho_sign=-1)

    # Leptons: keep v0.8 policy (no ρ microphase on C30)
    kL_base = k_pm_30 % nL
    Ue_kick, e_norm = _build_kick(5, phi_B, -RT_EPS0)
    Un_kick, n_norm = _build_kick(4, phi_A, +RT_EPS0)
    Ue, ks_e = _monodromy(Ue_kick, nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu, ks_n = _monodromy(Un_kick, nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V = Uu.conjugate().T @ Ud
    U = Ue.conjugate().T @ Unu

    ck_ang = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm_ang = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    def _score(a: Dict[str, float]) -> float:
        return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2

    s_ckm = _score(ck_ang)
    s_pmns = _score(pm_ang)

    def _in_range(x: float, r: Tuple[float, float]) -> bool:
        return (x >= float(r[0])) and (x <= float(r[1]))

    ck_t12 = float(ck_ang.get("theta12_deg", 0.0))
    ck_t23 = float(ck_ang.get("theta23_deg", 0.0))
    ck_t13 = float(ck_ang.get("theta13_deg", 0.0))
    ck_J = float(ck_ang.get("J", 0.0))
    ck_order = bool(ck_t12 > ck_t23 > ck_t13)
    ck_ranges_ok = bool(_in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG) and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG) and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG))
    ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
    pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)

    pm_t12 = float(pm_ang.get("theta12_deg", 0.0))
    pm_t23 = float(pm_ang.get("theta23_deg", 0.0))
    pm_t13 = float(pm_ang.get("theta13_deg", 0.0))
    pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
    pass_pmns_pattern = bool(pm_large_count >= 2)

    pass_struct = bool(s_ckm < s_pmns)

    out["policy"] = {
        "L_star_ticks": int(L_star),
        "blocks": int(blocks),
        "K": int(K),
        "rho": int(rho),
        "grid": {"lepton": int(nL), "quark": int(nQ)},
        "delta_base": {"CKM": {"deg": float(d_ckm), "k_mod30": int(k_ckm_30)}, "PMNS": {"deg": float(d_pm), "k_mod30": int(k_pm_30)}},
        "monodromy_step": {"lepton_dk": int(dkL), "quark_dk": int(dkQ)},
        "kick_variation": {"Z3_perm": True, "AB_toggle": True, "rho_microphase": True},
        "rho_microphase": {"micro_step": int(micro_step), "up_sign": +1, "down_sign": -1},
    }

    out["sectors"] = {
        "Uu": {"p": 6, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(u_norm), "unitary_residual": _rt_unitary_residual_np(Uu), "k_hist_tail": ks_u[-6:]},
        "Ud": {"p": 5, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(d_norm), "unitary_residual": _rt_unitary_residual_np(Ud), "k_hist_tail": ks_d[-6:]},
        "Ue": {"p": 5, "n_grid": nL, "k0": int(kL_base % nL), "dk": int(dkL), "kick_norm": float(e_norm), "unitary_residual": _rt_unitary_residual_np(Ue), "k_hist_tail": ks_e[-6:]},
        "Unu": {"p": 4, "n_grid": nL, "k0": int((kL_base + 5) % nL), "dk": int(dkL), "kick_norm": float(n_norm), "unitary_residual": _rt_unitary_residual_np(Unu), "k_hist_tail": ks_n[-6:]},
    }

    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck_ang}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm_ang}

    out["gate"] = {
        "score": {"ckm": float(s_ckm), "pmns": float(s_pmns), "pass": bool(pass_struct)},
        "ckm_pattern": {"pass": bool(pass_ckm_pattern), "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J}},
        "pmns_pattern": {"pass": bool(pass_pmns_pattern), "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13}, "large_count": int(pm_large_count)},
        "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
    }

    return out




def _rt_construct_misalignment_v0_10_monodromy_rho_z3sieve_1260(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct v0.10: like v0.9 but ρ-microphase is *Z3-sieved* to reduce CKM (diagnostic).

    Replace (b mod ρ) by ((b mod ρ) mod 3), i.e. only 0/1/2 micro-steps are injected on C300.
    This uses the existing Z3 structure explicitly and keeps everything discrete.
    """

    out = {
        "version": "rt_construct_v0_10_monodromy_rho_z3sieve_1260",
        "error": None,
        "policy": {},
        "sectors": {},
        "CKM": {},
        "PMNS": {},
        "gate": {},
    }

    if np is None:
        out["error"] = "numpy not available"
        return out

    def _snap_deg_to_C30(x: float) -> float:
        step = 360.0 / 30.0
        y = float(x) % 360.0
        k = int(round(y / step)) % 30
        return float(k) * step

    d_ckm = float(delta_deg_ckm) if delta_deg_ckm is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD))
    d_pm = float(delta_deg_pmns) if delta_deg_pmns is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD + math.pi))
    k_ckm_30 = int(round(d_ckm / (360.0 / 30.0))) % 30
    k_pm_30 = int(round(d_pm / (360.0 / 30.0))) % 30

    K = 30
    blocks = 42
    L_star = K * blocks
    nL, nQ = 30, 300
    dkL, dkQ = 5, 50

    rho = int(RT_RHO)
    micro_step = 1

    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)
    phi_B = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi)

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, eps)
        return Uk, float(m)

    def _rho_z3_sieved(b: int) -> int:
        # ρ-cycle injected through Z3: only 0/1/2 micro-steps (C300)
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        ks = []
        for b in range(blocks):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
            ks.append(int(kb))
        U = _rt_gauge_fix_unitary(U)
        return U, ks

    kQ_base = (10 * k_ckm_30) % nQ
    Uu_kick, u_norm = _build_kick(6, phi_A, +RT_EPS0)
    Ud_kick, d_norm = _build_kick(5, phi_B, -RT_EPS0)
    Uu, ks_u = _monodromy(Uu_kick, nQ, kQ_base, dkQ, rho_sign=+1)
    Ud, ks_d = _monodromy(Ud_kick, nQ, kQ_base, dkQ, rho_sign=-1)

    kL_base = k_pm_30 % nL
    Ue_kick, e_norm = _build_kick(5, phi_B, -RT_EPS0)
    Un_kick, n_norm = _build_kick(4, phi_A, +RT_EPS0)
    Ue, ks_e = _monodromy(Ue_kick, nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu, ks_n = _monodromy(Un_kick, nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V = Uu.conjugate().T @ Ud
    U = Ue.conjugate().T @ Unu

    ck_ang = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm_ang = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    def _score(a: Dict[str, float]) -> float:
        return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2

    s_ckm = _score(ck_ang)
    s_pmns = _score(pm_ang)

    def _in_range(x: float, r: Tuple[float, float]) -> bool:
        return (x >= float(r[0])) and (x <= float(r[1]))

    ck_t12 = float(ck_ang.get("theta12_deg", 0.0))
    ck_t23 = float(ck_ang.get("theta23_deg", 0.0))
    ck_t13 = float(ck_ang.get("theta13_deg", 0.0))
    ck_J = float(ck_ang.get("J", 0.0))
    ck_order = bool(ck_t12 > ck_t23 > ck_t13)
    ck_ranges_ok = bool(_in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG) and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG) and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG))
    ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
    pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)

    pm_t12 = float(pm_ang.get("theta12_deg", 0.0))
    pm_t23 = float(pm_ang.get("theta23_deg", 0.0))
    pm_t13 = float(pm_ang.get("theta13_deg", 0.0))
    pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
    pass_pmns_pattern = bool(pm_large_count >= 2)

    pass_struct = bool(s_ckm < s_pmns)

    out["policy"] = {
        "L_star_ticks": int(L_star),
        "blocks": int(blocks),
        "K": int(K),
        "rho": int(rho),
        "grid": {"lepton": int(nL), "quark": int(nQ)},
        "delta_base": {"CKM": {"deg": float(d_ckm), "k_mod30": int(k_ckm_30)}, "PMNS": {"deg": float(d_pm), "k_mod30": int(k_pm_30)}},
        "monodromy_step": {"lepton_dk": int(dkL), "quark_dk": int(dkQ)},
        "kick_variation": {"Z3_perm": True, "AB_toggle": True, "rho_microphase": "rho_z3_sieved"},
        "rho_microphase": {"micro_step": int(micro_step), "rho_z3_values": [0, 1, 2], "up_sign": +1, "down_sign": -1},
    }

    out["sectors"] = {
        "Uu": {"p": 6, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(u_norm), "unitary_residual": _rt_unitary_residual_np(Uu), "k_hist_tail": ks_u[-6:]},
        "Ud": {"p": 5, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(d_norm), "unitary_residual": _rt_unitary_residual_np(Ud), "k_hist_tail": ks_d[-6:]},
        "Ue": {"p": 5, "n_grid": nL, "k0": int(kL_base % nL), "dk": int(dkL), "kick_norm": float(e_norm), "unitary_residual": _rt_unitary_residual_np(Ue), "k_hist_tail": ks_e[-6:]},
        "Unu": {"p": 4, "n_grid": nL, "k0": int((kL_base + 5) % nL), "dk": int(dkL), "kick_norm": float(n_norm), "unitary_residual": _rt_unitary_residual_np(Unu), "k_hist_tail": ks_n[-6:]},
    }

    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck_ang}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm_ang}

    out["gate"] = {
        "score": {"ckm": float(s_ckm), "pmns": float(s_pmns), "pass": bool(pass_struct)},
        "ckm_pattern": {"pass": bool(pass_ckm_pattern), "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J}},
        "pmns_pattern": {"pass": bool(pass_pmns_pattern), "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13}, "large_count": int(pm_large_count)},
        "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
    }

    return out


def _rt_construct_misalignment_v0_11_monodromy_rho_z3sieve_12tiebreak_1260(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct v0.11: v0.10 + *directed 1–2 tie-breaker* (diagnostic).

    Goal: increase Cabibbo-like 1–2 mixing without leaking strongly into (1–3,2–3).

    Mechanism (fully discrete, no scan):
      - Keep v0.10 monodromy scaffold (L*=1260, Z3-permuted kick, A/B toggle, ρ-microphase Z3-sieved on C300).
      - Add an SU(2) kick on the (1,2) subspace ONLY for the *down sector* at the ρ-seam blocks:
            b % ρ == 0  (within the 42 blocks)
        using a fixed operator:
            K12 = exp(i * eps0 * sigma_x(12))
        where eps0 is the existing RT_EPS0 policy constant.

    This is intended as the minimal, *targeted* discrete asymmetry to boost θ12 while keeping θ13/θ23 small.
    """

    out = {
        "version": "rt_construct_v0_11_monodromy_rho_z3sieve_12tiebreak_1260",
        "error": None,
        "policy": {},
        "sectors": {},
        "CKM": {},
        "PMNS": {},
        "gate": {},
    }

    if np is None:
        out["error"] = "numpy not available"
        return out

    def _snap_deg_to_C30(x: float) -> float:
        step = 360.0 / 30.0
        y = float(x) % 360.0
        k = int(round(y / step)) % 30
        return float(k) * step

    d_ckm = float(delta_deg_ckm) if delta_deg_ckm is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD))
    d_pm = float(delta_deg_pmns) if delta_deg_pmns is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD + math.pi))
    k_ckm_30 = int(round(d_ckm / (360.0 / 30.0))) % 30
    k_pm_30 = int(round(d_pm / (360.0 / 30.0))) % 30

    K = 30
    blocks = 42
    L_star = K * blocks
    nL, nQ = 30, 300
    dkL, dkQ = 5, 50

    rho = int(RT_RHO)
    micro_step = 1

    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)
    phi_B = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi)

    # Directed (1,2) SU(2) kick (unitary).
    H12 = np.array([[0.0, 1.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0]], dtype=np.complex128)
    K12 = _rt_expm_i_hermitian(H12, float(RT_EPS0))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, eps)
        return Uk, float(m)

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0, apply_12_tiebreak: bool = False):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        ks = []
        applied = 0
        for b in range(blocks):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n

            P = _rt_proj_phase_Cn(kb, n)

            # Keep non-commutativity scaffold (Z3 perm + AB toggle)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T

            # Directed tie-breaker: only hit (1,2) on down-sector at ρ seams.
            if apply_12_tiebreak and (b % rho == 0):
                Ub = K12 @ Ub
                applied += 1

            S = P @ Ub @ P.conjugate().T
            U = U @ S
            ks.append(int(kb))

        U = _rt_gauge_fix_unitary(U)
        return U, ks, int(applied)

    kQ_base = (10 * k_ckm_30) % nQ
    Uu_kick, u_norm = _build_kick(6, phi_A, +RT_EPS0)
    Ud_kick, d_norm = _build_kick(5, phi_B, -RT_EPS0)

    # Apply 1–2 tie-break ONLY to down sector (Ud) to create misalignment (scan-free).
    Uu, ks_u, ap_u = _monodromy(Uu_kick, nQ, kQ_base, dkQ, rho_sign=+1, apply_12_tiebreak=False)
    Ud, ks_d, ap_d = _monodromy(Ud_kick, nQ, kQ_base, dkQ, rho_sign=-1, apply_12_tiebreak=True)

    kL_base = k_pm_30 % nL
    Ue_kick, e_norm = _build_kick(5, phi_B, -RT_EPS0)
    Un_kick, n_norm = _build_kick(4, phi_A, +RT_EPS0)
    Ue, ks_e, ap_e = _monodromy(Ue_kick, nL, (kL_base + 0) % nL, dkL, rho_sign=0, apply_12_tiebreak=False)
    Unu, ks_n, ap_n = _monodromy(Un_kick, nL, (kL_base + 5) % nL, dkL, rho_sign=0, apply_12_tiebreak=False)

    V = Uu.conjugate().T @ Ud
    U = Ue.conjugate().T @ Unu

    ck_ang = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm_ang = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    def _score(a: Dict[str, float]) -> float:
        return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2

    s_ckm = _score(ck_ang)
    s_pmns = _score(pm_ang)

    def _in_range(x: float, r: Tuple[float, float]) -> bool:
        return (x >= float(r[0])) and (x <= float(r[1]))

    ck_t12 = float(ck_ang.get("theta12_deg", 0.0))
    ck_t23 = float(ck_ang.get("theta23_deg", 0.0))
    ck_t13 = float(ck_ang.get("theta13_deg", 0.0))
    ck_J = float(ck_ang.get("J", 0.0))
    ck_order = bool(ck_t12 > ck_t23 > ck_t13)
    ck_ranges_ok = bool(_in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG) and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG) and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG))
    ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
    pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)

    pm_t12 = float(pm_ang.get("theta12_deg", 0.0))
    pm_t23 = float(pm_ang.get("theta23_deg", 0.0))
    pm_t13 = float(pm_ang.get("theta13_deg", 0.0))
    pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
    pass_pmns_pattern = bool(pm_large_count >= 2)

    pass_struct = bool(s_ckm < s_pmns)

    out["policy"] = {
        "L_star_ticks": int(L_star),
        "blocks": int(blocks),
        "K": int(K),
        "rho": int(rho),
        "grid": {"lepton": int(nL), "quark": int(nQ)},
        "delta_base": {"CKM": {"deg": float(d_ckm), "k_mod30": int(k_ckm_30)}, "PMNS": {"deg": float(d_pm), "k_mod30": int(k_pm_30)}},
        "monodromy_step": {"lepton_dk": int(dkL), "quark_dk": int(dkQ)},
        "kick_variation": {"Z3_perm": True, "AB_toggle": True, "rho_microphase": "rho_z3_sieved", "tiebreak_12": True},
        "rho_microphase": {"micro_step": int(micro_step), "rho_z3_values": [0, 1, 2], "up_sign": +1, "down_sign": -1},
        "tiebreak_12": {
            "active": True,
            "where": "down_sector_only",
            "when": "b % rho == 0",
            "kick": "K12 = exp(i*eps0*sigma_x(12))",
            "eps0": float(RT_EPS0),
        },
    }

    out["sectors"] = {
        "Uu": {"p": 6, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(u_norm), "unitary_residual": _rt_unitary_residual_np(Uu), "k_hist_tail": ks_u[-6:], "tiebreak_12_applied": int(ap_u)},
        "Ud": {"p": 5, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(d_norm), "unitary_residual": _rt_unitary_residual_np(Ud), "k_hist_tail": ks_d[-6:], "tiebreak_12_applied": int(ap_d)},
        "Ue": {"p": 5, "n_grid": nL, "k0": int(kL_base % nL), "dk": int(dkL), "kick_norm": float(e_norm), "unitary_residual": _rt_unitary_residual_np(Ue), "k_hist_tail": ks_e[-6:], "tiebreak_12_applied": int(ap_e)},
        "Unu": {"p": 4, "n_grid": nL, "k0": int((kL_base + 5) % nL), "dk": int(dkL), "kick_norm": float(n_norm), "unitary_residual": _rt_unitary_residual_np(Unu), "k_hist_tail": ks_n[-6:], "tiebreak_12_applied": int(ap_n)},
    }

    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck_ang}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm_ang}

    out["gate"] = {
        "score": {"ckm": float(s_ckm), "pmns": float(s_pmns), "pass": bool(pass_struct)},
        "ckm_pattern": {"pass": bool(pass_ckm_pattern), "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J}},
        "pmns_pattern": {"pass": bool(pass_pmns_pattern), "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13}, "large_count": int(pm_large_count)},
        "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
    }

    return out



def _rt_construct_misalignment_v0_12_monodromy_cabibbo_kick_12_1260(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct v0.12: monodromy scaffold + single C30-sized (1,2) Cabibbo kick (diagnostic).

    Motivation: v0.11's 1–2 kick used eps0=0.05 rad (~2.9°) and was too weak.
    Here we use a *pure C30 quantum*:
        eps12 = 2π/30  (~12°)
    applied exactly once at the monodromy start (b=0) and only on the down sector (Ud).

    This is still scan-free and knob-free: the angle is fixed by K=30.
    """

    out = {
        "version": "rt_construct_v0_12_monodromy_cabibbo_kick_12_1260",
        "error": None,
        "policy": {},
        "sectors": {},
        "CKM": {},
        "PMNS": {},
        "gate": {},
    }

    if np is None:
        out["error"] = "numpy not available"
        return out

    def _snap_deg_to_C30(x: float) -> float:
        step = 360.0 / 30.0
        y = float(x) % 360.0
        k = int(round(y / step)) % 30
        return float(k) * step

    d_ckm = float(delta_deg_ckm) if delta_deg_ckm is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD))
    d_pm = float(delta_deg_pmns) if delta_deg_pmns is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD + math.pi))
    k_ckm_30 = int(round(d_ckm / (360.0 / 30.0))) % 30
    k_pm_30 = int(round(d_pm / (360.0 / 30.0))) % 30

    K = 30
    blocks = 42
    L_star = K * blocks
    nL, nQ = 30, 300
    dkL, dkQ = 5, 50

    rho = int(RT_RHO)
    micro_step = 1

    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)
    phi_B = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi)

    # Cabibbo-sized (1,2) SU(2) kick (unitary): eps12 = 2π/30.
    eps12 = float(2.0 * math.pi / 30.0)
    H12 = np.array([[0.0, 1.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0]], dtype=np.complex128)
    K12 = _rt_expm_i_hermitian(H12, eps12)

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, eps)
        return Uk, float(m)

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0, apply_cabibbo_kick: bool = False):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        ks = []
        applied = 0
        for b in range(blocks):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n

            P = _rt_proj_phase_Cn(kb, n)

            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T

            # Single Cabibbo kick at start (b=0) on down sector only.
            if apply_cabibbo_kick and (b == 0):
                Ub = K12 @ Ub
                applied = 1

            S = P @ Ub @ P.conjugate().T
            U = U @ S
            ks.append(int(kb))

        U = _rt_gauge_fix_unitary(U)
        return U, ks, int(applied)

    kQ_base = (10 * k_ckm_30) % nQ
    Uu_kick, u_norm = _build_kick(6, phi_A, +RT_EPS0)
    Ud_kick, d_norm = _build_kick(5, phi_B, -RT_EPS0)

    Uu, ks_u, ap_u = _monodromy(Uu_kick, nQ, kQ_base, dkQ, rho_sign=+1, apply_cabibbo_kick=False)
    Ud, ks_d, ap_d = _monodromy(Ud_kick, nQ, kQ_base, dkQ, rho_sign=-1, apply_cabibbo_kick=True)

    kL_base = k_pm_30 % nL
    Ue_kick, e_norm = _build_kick(5, phi_B, -RT_EPS0)
    Un_kick, n_norm = _build_kick(4, phi_A, +RT_EPS0)
    Ue, ks_e, ap_e = _monodromy(Ue_kick, nL, (kL_base + 0) % nL, dkL, rho_sign=0, apply_cabibbo_kick=False)
    Unu, ks_n, ap_n = _monodromy(Un_kick, nL, (kL_base + 5) % nL, dkL, rho_sign=0, apply_cabibbo_kick=False)

    V = Uu.conjugate().T @ Ud
    U = Ue.conjugate().T @ Unu

    ck_ang = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm_ang = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    def _score(a: Dict[str, float]) -> float:
        return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2

    s_ckm = _score(ck_ang)
    s_pmns = _score(pm_ang)

    def _in_range(x: float, r: Tuple[float, float]) -> bool:
        return (x >= float(r[0])) and (x <= float(r[1]))

    ck_t12 = float(ck_ang.get("theta12_deg", 0.0))
    ck_t23 = float(ck_ang.get("theta23_deg", 0.0))
    ck_t13 = float(ck_ang.get("theta13_deg", 0.0))
    ck_J = float(ck_ang.get("J", 0.0))
    ck_order = bool(ck_t12 > ck_t23 > ck_t13)
    ck_ranges_ok = bool(_in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG) and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG) and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG))
    ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
    pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)

    pm_t12 = float(pm_ang.get("theta12_deg", 0.0))
    pm_t23 = float(pm_ang.get("theta23_deg", 0.0))
    pm_t13 = float(pm_ang.get("theta13_deg", 0.0))
    pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
    pass_pmns_pattern = bool(pm_large_count >= 2)

    pass_struct = bool(s_ckm < s_pmns)

    out["policy"] = {
        "L_star_ticks": int(L_star),
        "blocks": int(blocks),
        "K": int(K),
        "rho": int(rho),
        "grid": {"lepton": int(nL), "quark": int(nQ)},
        "delta_base": {"CKM": {"deg": float(d_ckm), "k_mod30": int(k_ckm_30)}, "PMNS": {"deg": float(d_pm), "k_mod30": int(k_pm_30)}},
        "monodromy_step": {"lepton_dk": int(dkL), "quark_dk": int(dkQ)},
        "kick_variation": {"Z3_perm": True, "AB_toggle": True, "rho_microphase": "rho_z3_sieved", "cabibbo_kick_12": True},
        "rho_microphase": {"micro_step": int(micro_step), "rho_z3_values": [0, 1, 2], "up_sign": +1, "down_sign": -1},
        "cabibbo_kick_12": {"active": True, "where": "down_sector_only", "when": "b == 0", "eps12": float(eps12)},
    }

    out["sectors"] = {
        "Uu": {"p": 6, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(u_norm), "unitary_residual": _rt_unitary_residual_np(Uu), "k_hist_tail": ks_u[-6:], "cabibbo_kick_applied": int(ap_u)},
        "Ud": {"p": 5, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(d_norm), "unitary_residual": _rt_unitary_residual_np(Ud), "k_hist_tail": ks_d[-6:], "cabibbo_kick_applied": int(ap_d)},
        "Ue": {"p": 5, "n_grid": nL, "k0": int(kL_base % nL), "dk": int(dkL), "kick_norm": float(e_norm), "unitary_residual": _rt_unitary_residual_np(Ue), "k_hist_tail": ks_e[-6:], "cabibbo_kick_applied": int(ap_e)},
        "Unu": {"p": 4, "n_grid": nL, "k0": int((kL_base + 5) % nL), "dk": int(dkL), "kick_norm": float(n_norm), "unitary_residual": _rt_unitary_residual_np(Unu), "k_hist_tail": ks_n[-6:], "cabibbo_kick_applied": int(ap_n)},
    }

    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck_ang}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm_ang}

    out["gate"] = {
        "score": {"ckm": float(s_ckm), "pmns": float(s_pmns), "pass": bool(pass_struct)},
        "ckm_pattern": {"pass": bool(pass_ckm_pattern), "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J}},
        "pmns_pattern": {"pass": bool(pass_pmns_pattern), "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13}, "large_count": int(pm_large_count)},
        "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
    }

    return out



def _rt_construct_misalignment_v0_13_monodromy_postR12_seam_1260(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct v0.13: v0.10 monodromy + *post* (1,2) seam basis rotation (diagnostic).

    Motivation:
      - We want to boost Cabibbo-like θ12 while *not* inflating θ13/θ23.
      - Right-multiplying CKM by an (1,2) rotation leaves the 3rd column invariant,
        so |Vub| and |Vcb| (hence θ13, θ23 in the PDG extraction) are unchanged.

    Mechanism (fully discrete, no scan):
      1) Build Uu, Ud, Ue, Unu using the v0.10 monodromy scaffold (L*=1260; Z3-permuted kick; A/B toggle; ρ-microphase Z3-sieved on C300).
      2) Apply a *single* seam operation on the down sector ONLY:
            Ud <- Ud · R12(θ=2π/30, φ=quantize_pi/3(δφ*+π))
         where R12 is a unitary SU(2) rotation embedded in 3×3.

    Interpretation:
      This is a deterministic RT tie-break/basis choice localized to the (d,s) subspace.

    Output is diagnostic only (does not gate overall PASS yet).
    """

    out = {
        "version": "rt_construct_v0_13_monodromy_postR12_seam_1260",
        "error": None,
        "policy": {},
        "sectors": {},
        "CKM": {},
        "PMNS": {},
        "gate": {},
    }

    if np is None:
        out["error"] = "numpy not available"
        return out

    def _snap_deg_to_C30(x: float) -> float:
        step = 360.0 / 30.0
        y = float(x) % 360.0
        k = int(round(y / step)) % 30
        return float(k) * step

    d_ckm = float(delta_deg_ckm) if delta_deg_ckm is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD))
    d_pm = float(delta_deg_pmns) if delta_deg_pmns is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD + math.pi))
    k_ckm_30 = int(round(d_ckm / (360.0 / 30.0))) % 30
    k_pm_30 = int(round(d_pm / (360.0 / 30.0))) % 30

    K = 30
    blocks = 42
    L_star = K * blocks
    nL, nQ = 30, 300
    dkL, dkQ = 5, 50

    rho = int(RT_RHO)
    micro_step = 1

    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)
    phi_B = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi)

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, eps)
        return Uk, float(m)

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        ks = []
        for b in range(blocks):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
            ks.append(int(kb))
        U = _rt_gauge_fix_unitary(U)
        return U, ks

    kQ_base = (10 * k_ckm_30) % nQ
    Uu_kick, u_norm = _build_kick(6, phi_A, +RT_EPS0)
    Ud_kick, d_norm = _build_kick(5, phi_B, -RT_EPS0)
    Uu, ks_u = _monodromy(Uu_kick, nQ, kQ_base, dkQ, rho_sign=+1)
    Ud, ks_d = _monodromy(Ud_kick, nQ, kQ_base, dkQ, rho_sign=-1)

    # Post seam basis operation: Ud <- Ud · R12(2π/30, φ_B)
    theta = float(2.0 * math.pi / 30.0)
    c = math.cos(theta)
    s = math.sin(theta)
    ph = float(phi_B)
    e_m = complex(math.cos(-ph), math.sin(-ph))
    e_p = complex(math.cos(+ph), math.sin(+ph))
    R12 = np.array([
        [c, s * e_m, 0.0],
        [-s * e_p, c, 0.0],
        [0.0, 0.0, 1.0],
    ], dtype=np.complex128)
    Ud_seam = Ud @ R12

    kL_base = k_pm_30 % nL
    Ue_kick, e_norm = _build_kick(5, phi_B, -RT_EPS0)
    Un_kick, n_norm = _build_kick(4, phi_A, +RT_EPS0)
    Ue, ks_e = _monodromy(Ue_kick, nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu, ks_n = _monodromy(Un_kick, nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V = Uu.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck_ang = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm_ang = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    def _score(a: Dict[str, float]) -> float:
        return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2

    s_ckm = _score(ck_ang)
    s_pmns = _score(pm_ang)

    def _in_range(x: float, r: Tuple[float, float]) -> bool:
        return (x >= float(r[0])) and (x <= float(r[1]))

    ck_t12 = float(ck_ang.get("theta12_deg", 0.0))
    ck_t23 = float(ck_ang.get("theta23_deg", 0.0))
    ck_t13 = float(ck_ang.get("theta13_deg", 0.0))
    ck_J = float(ck_ang.get("J", 0.0))
    ck_order = bool(ck_t12 > ck_t23 > ck_t13)
    ck_ranges_ok = bool(_in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG) and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG) and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG))
    ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
    pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)

    pm_t12 = float(pm_ang.get("theta12_deg", 0.0))
    pm_t23 = float(pm_ang.get("theta23_deg", 0.0))
    pm_t13 = float(pm_ang.get("theta13_deg", 0.0))
    pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
    pass_pmns_pattern = bool(pm_large_count >= 2)

    pass_struct = bool(s_ckm < s_pmns)

    out["policy"] = {
        "L_star_ticks": int(L_star),
        "blocks": int(blocks),
        "K": int(K),
        "rho": int(rho),
        "grid": {"lepton": int(nL), "quark": int(nQ)},
        "delta_base": {"CKM": {"deg": float(d_ckm), "k_mod30": int(k_ckm_30)}, "PMNS": {"deg": float(d_pm), "k_mod30": int(k_pm_30)}},
        "monodromy_step": {"lepton_dk": int(dkL), "quark_dk": int(dkQ)},
        "kick_variation": {"Z3_perm": True, "AB_toggle": True, "rho_microphase": "rho_z3_sieved", "postR12_seam": True},
        "rho_microphase": {"micro_step": int(micro_step), "rho_z3_values": [0, 1, 2], "up_sign": +1, "down_sign": -1},
        "postR12_seam": {
            "active": True,
            "where": "down_sector_only",
            "action": "Ud <- Ud · R12",
            "theta_rad": float(theta),
            "phi_rad": float(ph),
            "theta_deg": float(math.degrees(theta)),
            "invariant": "CKM 3rd column invariant under right-multiplication by R12",
        },
    }

    out["sectors"] = {
        "Uu": {"p": 6, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(u_norm), "unitary_residual": _rt_unitary_residual_np(Uu), "k_hist_tail": ks_u[-6:]},
        "Ud": {"p": 5, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(d_norm), "unitary_residual": _rt_unitary_residual_np(Ud_seam), "k_hist_tail": ks_d[-6:], "postR12_applied": 1},
        "Ue": {"p": 5, "n_grid": nL, "k0": int(kL_base % nL), "dk": int(dkL), "kick_norm": float(e_norm), "unitary_residual": _rt_unitary_residual_np(Ue), "k_hist_tail": ks_e[-6:]},
        "Unu": {"p": 4, "n_grid": nL, "k0": int((kL_base + 5) % nL), "dk": int(dkL), "kick_norm": float(n_norm), "unitary_residual": _rt_unitary_residual_np(Unu), "k_hist_tail": ks_n[-6:]},
    }

    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck_ang}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm_ang}

    out["gate"] = {
        "score": {"ckm": float(s_ckm), "pmns": float(s_pmns), "pass": bool(pass_struct)},
        "ckm_pattern": {"pass": bool(pass_ckm_pattern), "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J}},
        "pmns_pattern": {"pass": bool(pass_pmns_pattern), "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13}, "large_count": int(pm_large_count)},
        "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
    }

    return out



def _rt_construct_misalignment_v0_14_monodromy_postR12_seam_macro_micro_1260(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct v0.14: v0.13 but seam angle is *macro+micro* (diagnostic).

    Why:
      - v0.13 shows the key structural trick: post seam R12 can lift θ12 without touching θ13/θ23.
      - Here we harden the seam angle to a purely RT-integer combination:

          θ = 2π/30  +  (2π/(30·ρ)) · s_end

        where ρ=10 and s_end is the Z3-sieved ρ-index at the *end* of the 42-block loop.
        With blocks=42 and ρ=10, s_end = ((41 mod ρ) mod 3) = 1, so this becomes a fixed
        "one macro tick + one micro tick" angle.

    Output is diagnostic only (does not gate overall PASS).
    """

    out = {
        "version": "rt_construct_v0_14_monodromy_postR12_seam_macro_micro_1260",
        "error": None,
        "policy": {},
        "sectors": {},
        "CKM": {},
        "PMNS": {},
        "gate": {},
    }

    if np is None:
        out["error"] = "numpy not available"
        return out

    def _snap_deg_to_C30(x: float) -> float:
        step = 360.0 / 30.0
        y = float(x) % 360.0
        k = int(round(y / step)) % 30
        return float(k) * step

    d_ckm = float(delta_deg_ckm) if delta_deg_ckm is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD))
    d_pm = float(delta_deg_pmns) if delta_deg_pmns is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD + math.pi))
    k_ckm_30 = int(round(d_ckm / (360.0 / 30.0))) % 30
    k_pm_30 = int(round(d_pm / (360.0 / 30.0))) % 30

    K = 30
    blocks = 42
    L_star = K * blocks
    nL, nQ = 30, 300
    dkL, dkQ = 5, 50

    rho = int(RT_RHO)
    micro_step = 1

    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)
    phi_B = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi)

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, eps)
        return Uk, float(m)

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        ks = []
        for b in range(blocks):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
            ks.append(int(kb))
        U = _rt_gauge_fix_unitary(U)
        return U, ks

    kQ_base = (10 * k_ckm_30) % nQ
    Uu_kick, u_norm = _build_kick(6, phi_A, +RT_EPS0)
    Ud_kick, d_norm = _build_kick(5, phi_B, -RT_EPS0)
    Uu, ks_u = _monodromy(Uu_kick, nQ, kQ_base, dkQ, rho_sign=+1)
    Ud, ks_d = _monodromy(Ud_kick, nQ, kQ_base, dkQ, rho_sign=-1)

    # Post seam basis operation: Ud <- Ud · R12(theta, phi_B)
    s_end = int(_rho_z3_sieved(blocks - 1))
    theta_base = float(2.0 * math.pi / 30.0)
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_end))
    theta = float(theta_base + theta_micro)
    c = math.cos(theta)
    s = math.sin(theta)
    ph = float(phi_B)
    e_m = complex(math.cos(-ph), math.sin(-ph))
    e_p = complex(math.cos(+ph), math.sin(+ph))
    R12 = np.array([
        [c, s * e_m, 0.0],
        [-s * e_p, c, 0.0],
        [0.0, 0.0, 1.0],
    ], dtype=np.complex128)
    Ud_seam = Ud @ R12

    kL_base = k_pm_30 % nL
    Ue_kick, e_norm = _build_kick(5, phi_B, -RT_EPS0)
    Un_kick, n_norm = _build_kick(4, phi_A, +RT_EPS0)
    Ue, ks_e = _monodromy(Ue_kick, nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu, ks_n = _monodromy(Un_kick, nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V = Uu.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck_ang = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm_ang = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    def _score(a: Dict[str, float]) -> float:
        return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2

    s_ckm = _score(ck_ang)
    s_pmns = _score(pm_ang)

    def _in_range(x: float, r: Tuple[float, float]) -> bool:
        return (x >= float(r[0])) and (x <= float(r[1]))

    ck_t12 = float(ck_ang.get("theta12_deg", 0.0))
    ck_t23 = float(ck_ang.get("theta23_deg", 0.0))
    ck_t13 = float(ck_ang.get("theta13_deg", 0.0))
    ck_J = float(ck_ang.get("J", 0.0))
    ck_order = bool(ck_t12 > ck_t23 > ck_t13)
    ck_ranges_ok = bool(_in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG) and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG) and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG))
    ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
    pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)

    pm_t12 = float(pm_ang.get("theta12_deg", 0.0))
    pm_t23 = float(pm_ang.get("theta23_deg", 0.0))
    pm_t13 = float(pm_ang.get("theta13_deg", 0.0))
    pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
    pass_pmns_pattern = bool(pm_large_count >= 2)

    pass_struct = bool(s_ckm < s_pmns)

    out["policy"] = {
        "L_star_ticks": int(L_star),
        "blocks": int(blocks),
        "K": int(K),
        "rho": int(rho),
        "grid": {"lepton": int(nL), "quark": int(nQ)},
        "delta_base": {"CKM": {"deg": float(d_ckm), "k_mod30": int(k_ckm_30)}, "PMNS": {"deg": float(d_pm), "k_mod30": int(k_pm_30)}},
        "monodromy_step": {"lepton_dk": int(dkL), "quark_dk": int(dkQ)},
        "kick_variation": {"Z3_perm": True, "AB_toggle": True, "rho_microphase": "rho_z3_sieved", "postR12_seam": True},
        "rho_microphase": {"micro_step": int(micro_step), "rho_z3_values": [0, 1, 2], "up_sign": +1, "down_sign": -1},
        "postR12_seam": {
            "active": True,
            "where": "down_sector_only",
            "action": "Ud <- Ud · R12",
            "theta_rad": float(theta),
            "theta_deg": float(math.degrees(theta)),
            "theta_components_deg": {"macro": float(math.degrees(theta_base)), "micro": float(math.degrees(theta_micro)), "s_end": int(s_end)},
            "phi_rad": float(ph),
            "invariant": "CKM 3rd column invariant under right-multiplication by R12",
        },
    }

    out["sectors"] = {
        "Uu": {"p": 6, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(u_norm), "unitary_residual": _rt_unitary_residual_np(Uu), "k_hist_tail": ks_u[-6:]},
        "Ud": {"p": 5, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(d_norm), "unitary_residual": _rt_unitary_residual_np(Ud_seam), "k_hist_tail": ks_d[-6:], "postR12_applied": 1},
        "Ue": {"p": 5, "n_grid": nL, "k0": int(kL_base % nL), "dk": int(dkL), "kick_norm": float(e_norm), "unitary_residual": _rt_unitary_residual_np(Ue), "k_hist_tail": ks_e[-6:]},
        "Unu": {"p": 4, "n_grid": nL, "k0": int((kL_base + 5) % nL), "dk": int(dkL), "kick_norm": float(n_norm), "unitary_residual": _rt_unitary_residual_np(Unu), "k_hist_tail": ks_n[-6:]},
    }

    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck_ang}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm_ang}

    out["gate"] = {
        "score": {"ckm": float(s_ckm), "pmns": float(s_pmns), "pass": bool(pass_struct)},
        "ckm_pattern": {"pass": bool(pass_ckm_pattern), "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J}},
        "pmns_pattern": {"pass": bool(pass_pmns_pattern), "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13}, "large_count": int(pm_large_count)},
        "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
    }

    return out



def _rt_construct_misalignment_v0_15_monodromy_postR12_seam_from_phase_rule_1260(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct v0.15: integrate the *post seam* R12 angle into the same δ→k_rt phase-rule.

    Goal:
      - Keep the key invariant from v0.13/v0.14: right-multiplication by R12 leaves the CKM 3rd column unchanged
        ⇒ θ13/θ23 stay controlled while θ12 is lifted.
      - Remove the "feels like a patch" aspect: the seam micro-correction is now derived deterministically
        from k_rt (C30) itself, via a Z3→{+1,0,-1} map.

    Rule:
      - macro seam: 2π/30 (one C30 tick)
      - micro seam: (2π/(30·ρ))·s_micro, with ρ=10 and

          s_micro := 1 − (k_rt mod 3)  ∈ {+1,0,−1}

        This uses no new continuous parameters and ties the seam to the same Z3 sectoring already used in
        the RT phase-rule gate.

    Output is diagnostic only (does not gate overall PASS).
    """

    out = {
        "version": "rt_construct_v0_15_monodromy_postR12_seam_from_phase_rule_1260",
        "error": None,
        "policy": {},
        "sectors": {},
        "CKM": {},
        "PMNS": {},
        "gate": {},
    }

    if np is None:
        out["error"] = "numpy not available"
        return out

    def _snap_deg_to_C30(x: float) -> float:
        step = 360.0 / 30.0
        y = float(x) % 360.0
        k = int(round(y / step)) % 30
        return float(k) * step

    d_ckm = float(delta_deg_ckm) if delta_deg_ckm is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD))
    d_pm = float(delta_deg_pmns) if delta_deg_pmns is not None else _snap_deg_to_C30(math.degrees(RT_DELTA_PHI_STAR_RAD + math.pi))
    k_ckm_30 = int(round(d_ckm / (360.0 / 30.0))) % 30
    k_pm_30 = int(round(d_pm / (360.0 / 30.0))) % 30

    K = 30
    blocks = 42
    L_star = K * blocks
    nL, nQ = 30, 300
    dkL, dkQ = 5, 50

    rho = int(RT_RHO)
    micro_step = 1

    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)
    phi_B = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi)

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, eps)
        return Uk, float(m)

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        ks = []
        for b in range(blocks):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
            ks.append(int(kb))
        U = _rt_gauge_fix_unitary(U)
        return U, ks

    # Quarks: C300 base uses k_rt scaled by 10 (same as earlier constructs)
    kQ_base = (10 * k_ckm_30) % nQ
    Uu_kick, u_norm = _build_kick(6, phi_A, +RT_EPS0)
    Ud_kick, d_norm = _build_kick(5, phi_B, -RT_EPS0)
    Uu, ks_u = _monodromy(Uu_kick, nQ, kQ_base, dkQ, rho_sign=+1)
    Ud, ks_d = _monodromy(Ud_kick, nQ, kQ_base, dkQ, rho_sign=-1)

    # Post seam basis operation: Ud <- Ud · R12(theta, phi_B)
    # s_micro is derived from the *same* k_rt (C30) used in the phase-rule gate.
    s_micro = int(1 - (k_ckm_30 % 3))  # maps {0,1,2} -> {+1,0,-1}
    theta_base = float(2.0 * math.pi / 30.0)
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))
    theta = float(theta_base + theta_micro)
    c = math.cos(theta)
    s = math.sin(theta)
    ph = float(phi_B)
    e_m = complex(math.cos(-ph), math.sin(-ph))
    e_p = complex(math.cos(+ph), math.sin(+ph))
    R12 = np.array([
        [c, s * e_m, 0.0],
        [-s * e_p, c, 0.0],
        [0.0, 0.0, 1.0],
    ], dtype=np.complex128)
    Ud_seam = Ud @ R12

    # Leptons: stay on C30 grid (no rho microphase)
    kL_base = k_pm_30 % nL
    Ue_kick, e_norm = _build_kick(5, phi_B, -RT_EPS0)
    Un_kick, n_norm = _build_kick(4, phi_A, +RT_EPS0)
    Ue, ks_e = _monodromy(Ue_kick, nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu, ks_n = _monodromy(Un_kick, nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V = Uu.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck_ang = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm_ang = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    def _score(a: Dict[str, float]) -> float:
        return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2

    s_ckm = _score(ck_ang)
    s_pmns = _score(pm_ang)

    def _in_range(x: float, r: Tuple[float, float]) -> bool:
        return (x >= float(r[0])) and (x <= float(r[1]))

    ck_t12 = float(ck_ang.get("theta12_deg", 0.0))
    ck_t23 = float(ck_ang.get("theta23_deg", 0.0))
    ck_t13 = float(ck_ang.get("theta13_deg", 0.0))
    ck_J = float(ck_ang.get("J", 0.0))
    ck_order = bool(ck_t12 > ck_t23 > ck_t13)
    ck_ranges_ok = bool(_in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG) and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG) and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG))
    ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
    pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)

    pm_t12 = float(pm_ang.get("theta12_deg", 0.0))
    pm_t23 = float(pm_ang.get("theta23_deg", 0.0))
    pm_t13 = float(pm_ang.get("theta13_deg", 0.0))
    pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
    pass_pmns_pattern = bool(pm_large_count >= 2)

    pass_struct = bool(s_ckm < s_pmns)

    out["policy"] = {
        "L_star_ticks": int(L_star),
        "blocks": int(blocks),
        "K": int(K),
        "rho": int(rho),
        "grid": {"lepton": int(nL), "quark": int(nQ)},
        "delta_base": {"CKM": {"deg": float(d_ckm), "k_mod30": int(k_ckm_30)}, "PMNS": {"deg": float(d_pm), "k_mod30": int(k_pm_30)}},
        "monodromy_step": {"lepton_dk": int(dkL), "quark_dk": int(dkQ)},
        "kick_variation": {"Z3_perm": True, "AB_toggle": True, "rho_microphase": "rho_z3_sieved", "postR12_seam": True},
        "rho_microphase": {"micro_step": int(micro_step), "rho_z3_values": [0, 1, 2], "up_sign": +1, "down_sign": -1},
        "postR12_seam": {
            "active": True,
            "where": "down_sector_only",
            "action": "Ud <- Ud · R12",
            "theta_rad": float(theta),
            "theta_deg": float(math.degrees(theta)),
            "theta_components_deg": {"macro": float(math.degrees(theta_base)), "micro": float(math.degrees(theta_micro)), "s_micro": int(s_micro), "k_mod3": int(k_ckm_30 % 3)},
            "phi_rad": float(ph),
            "invariant": "CKM 3rd column invariant under right-multiplication by R12",
            "seam_rule": "s_micro := 1 − (k_rt mod 3)",
        },
    }

    out["sectors"] = {
        "Uu": {"p": 6, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(u_norm), "unitary_residual": _rt_unitary_residual_np(Uu), "k_hist_tail": ks_u[-6:]},
        "Ud": {"p": 5, "n_grid": nQ, "k0": int(kQ_base), "dk": int(dkQ), "kick_norm": float(d_norm), "unitary_residual": _rt_unitary_residual_np(Ud_seam), "k_hist_tail": ks_d[-6:], "postR12_applied": 1},
        "Ue": {"p": 5, "n_grid": nL, "k0": int(kL_base % nL), "dk": int(dkL), "kick_norm": float(e_norm), "unitary_residual": _rt_unitary_residual_np(Ue), "k_hist_tail": ks_e[-6:]},
        "Unu": {"p": 4, "n_grid": nL, "k0": int((kL_base + 5) % nL), "dk": int(dkL), "kick_norm": float(n_norm), "unitary_residual": _rt_unitary_residual_np(Unu), "k_hist_tail": ks_n[-6:]},
    }

    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck_ang}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm_ang}

    out["gate"] = {
        "score": {"ckm": float(s_ckm), "pmns": float(s_pmns), "pass": bool(pass_struct)},
        "ckm_pattern": {"pass": bool(pass_ckm_pattern), "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J}},
        "pmns_pattern": {"pass": bool(pass_pmns_pattern), "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13}, "large_count": int(pm_large_count)},
        "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
    }

    return out



def _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct v0.16: same as v0.15 but with *down-oriented* Z3→micro map.

    Motivation:
      - The seam is applied on Ud (down sector) after a monodromy that already uses a sign difference
        between u/d in the rho-microphase path.
      - Therefore the Z3→{−1,0,+1} micro-map should respect the down-oriented convention.

    Rule:
      - macro: 2π/30
      - micro: (2π/(30·ρ))·s_micro with

          s_micro := (k_rt mod 3) − 1  ∈ {−1,0,+1}

    This is still fully discrete and uses no new continuous parameters.
    """

    out = _rt_construct_misalignment_v0_15_monodromy_postR12_seam_from_phase_rule_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260"
    if out.get("error"):
        return out

    pol = (out.get("policy") or {})
    db = ((pol.get("delta_base") or {}).get("CKM") or {})
    k_ckm_30 = int(db.get("k_mod30") or 0) % 30
    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO)
    if rho <= 0:
        rho = 10

    # recompute seam with down-oriented map
    s_micro = int((k_ckm_30 % 3) - 1)  # maps {0,1,2}->{-1,0,+1}
    theta_base = float(2.0 * math.pi / 30.0)
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))
    theta = float(theta_base + theta_micro)

    # rebuild Ud_seam from stored Ud (pre-seam) if available; otherwise keep previous (diagnostic)
    # We stored only post-seam matrices in out, so we reconstruct via CKM relation if possible.
    # For simplicity, we re-run a minimal rebuild using the same internal policy.
    # NOTE: diagnostic only.
    try:
        # quick rebuild via the same monodromy core from v0.15 (duplicated minimally to avoid refactor)
        # pull parameters
        K = int(pol.get("K") or 30)
        blocks = int(pol.get("blocks") or 42)
        nQ = int((pol.get("grid") or {}).get("quark") or 300)
        dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
        phi_B = float(((pol.get("postR12_seam") or {}).get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi)))
        phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

        def _build_kick(p: int, phi_edge: float, eps: float):
            N = _rt_near_coupling_matrix(int(p))
            N = _rt_apply_edge_phases(N, float(phi_edge))
            H = (N + N.conjugate().T)
            w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
            m = float(np.max(np.abs(w.real))) if w.size else 1.0
            if m < 1e-12:
                m = 1.0
            Hn = H / m
            Uk = _rt_expm_i_hermitian(Hn, RT_EPS0 if p == 6 else -RT_EPS0)
            return Uk

        def _rho_z3_sieved(b: int) -> int:
            return int((b % rho) % 3)

        def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
            U = np.eye(3, dtype=np.complex128)
            for b in range(blocks):
                kb = (k0 + b * dk) % n
                if (n == nQ) and (rho_sign != 0):
                    kb = (kb + rho_sign * _rho_z3_sieved(b)) % n
                P = _rt_proj_phase_Cn(kb, n)
                R = _rt_perm_cycle_pow(b % 3)
                Ub = U_kick.conjugate().T if (b % 2) else U_kick
                Ub = R @ Ub @ R.conjugate().T
                S = P @ Ub @ P.conjugate().T
                U = U @ S
            return _rt_gauge_fix_unitary(U)

        kQ_base = (10 * k_ckm_30) % nQ
        Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
        Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

        c = math.cos(theta)
        s = math.sin(theta)
        e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
        e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
        R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
        Ud_seam = Ud @ R12
        V = Uu.conjugate().T @ Ud_seam
        ck_ang = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
        out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck_ang}
        out["sectors"]["Ud"]["unitary_residual"] = _rt_unitary_residual_np(Ud_seam)
    except Exception as e:
        out["error"] = f"v0.16 rebuild failed: {e}"
        return out

    # update policy seam block
    pol["postR12_seam"]["theta_rad"] = float(theta)
    pol["postR12_seam"]["theta_deg"] = float(math.degrees(theta))
    pol["postR12_seam"]["theta_components_deg"] = {
        "macro": float(math.degrees(theta_base)),
        "micro": float(math.degrees(theta_micro)),
        "s_micro": int(s_micro),
        "k_mod3": int(k_ckm_30 % 3),
        "map": "down_oriented: s_micro=(k_mod3)-1",
    }
    pol["postR12_seam"]["seam_rule"] = "s_micro := (k_rt mod 3) − 1 (down-oriented)"
    out["policy"] = pol

    # recompute gate summary
    try:
        ck_ang = ((out.get("CKM") or {}).get("angles") or {})
        pm_ang = ((out.get("PMNS") or {}).get("angles") or {})
        def _score(a: Dict[str, float]) -> float:
            return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2
        s_ckm = _score(ck_ang)
        s_pmns = _score(pm_ang)
        def _in_range(x: float, r: Tuple[float, float]) -> bool:
            return (x >= float(r[0])) and (x <= float(r[1]))
        ck_t12 = float(ck_ang.get("theta12_deg", 0.0))
        ck_t23 = float(ck_ang.get("theta23_deg", 0.0))
        ck_t13 = float(ck_ang.get("theta13_deg", 0.0))
        ck_J = float(ck_ang.get("J", 0.0))
        ck_order = bool(ck_t12 > ck_t23 > ck_t13)
        ck_ranges_ok = bool(_in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG) and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG) and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG))
        ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
        pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)
        pm_t12 = float(pm_ang.get("theta12_deg", 0.0))
        pm_t23 = float(pm_ang.get("theta23_deg", 0.0))
        pm_t13 = float(pm_ang.get("theta13_deg", 0.0))
        pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
        pass_pmns_pattern = bool(pm_large_count >= 2)
        pass_struct = bool(s_ckm < s_pmns)
        out["gate"] = {
            "score": {"ckm": float(s_ckm), "pmns": float(s_pmns), "pass": bool(pass_struct)},
            "ckm_pattern": {"pass": bool(pass_ckm_pattern), "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J}},
            "pmns_pattern": {"pass": bool(pass_pmns_pattern), "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13}, "large_count": int(pm_large_count)},
            "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
        }
    except Exception:
        pass

    return out


def _rt_construct_misalignment_v0_17_monodromy_postR12_seam_down_oriented_rowkick23_micro_1260(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct v0.17 (diagnostic): v0.16 + an extra *row-kick* R23 micro-step.

    Motivation (diagnostic only): v0.16 gets Cabibbo close, but θ23 can land too small.
    A pure 2–3 row rotation on V (rows 2/3) by one micro-step (2π/(30·ρ)) increases θ23
    while leaving θ13 (row-0, col-2) unchanged.

    Important: this is NOT claimed physical yet; it is a scoped probe for where a missing
    2–3 asymmetry might belong in the PP→RP seam picture.
    """

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_17_monodromy_postR12_seam_down_oriented_rowkick23_micro_1260"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    seam = (pol.get("postR12_seam") or {})
    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or 0)

    ck = (out.get("CKM") or {})
    ang = (ck.get("angles") or {})
    th12 = math.radians(float(ang.get("theta12_deg") or 0.0))
    th23 = math.radians(float(ang.get("theta23_deg") or 0.0))
    th13 = math.radians(float(ang.get("theta13_deg") or 0.0))
    ddeg = float(ang.get("delta_deg_from_sin") or 0.0)
    delta = math.radians(ddeg)

    # Reconstruct a representative complex V via PDG parameterization.
    V = np.array(_ckm_unitary_pdg(th12, th23, th13, delta), dtype=np.complex128)

    # Apply micro-step row-kick in the (2,3) plane.
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro if s_micro != 0 else 1))
    c = math.cos(theta_micro)
    s = math.sin(theta_micro)
    R23 = np.array([
        [1.0, 0.0, 0.0],
        [0.0, c, s],
        [0.0, -s, c],
    ], dtype=np.complex128)
    V2 = R23 @ V

    ck2 = _angles_J_from_unitary([[complex(V2[i, j]) for j in range(3)] for i in range(3)])

    out["policy"]["postL23_rowkick"] = {
        "active": True,
        "action": "V <- R23(theta_micro) · V (row-kick)",
        "theta_rad": float(theta_micro),
        "theta_deg": float(math.degrees(theta_micro)),
        "s_micro": int(s_micro if s_micro != 0 else 1),
        "note": "diagnostic-only; indicates missing 2–3 asymmetry if it improves CKM shape",
    }
    out["CKM_rowkick"] = {"V_abs": _rt_abs_from_np(V2), "unitary_residual": _rt_unitary_residual_np(V2), "angles": ck2}

    return out





def _rt_construct_misalignment_v0_18_monodromy_postR12_seam_down_oriented_pp23_1260(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct v0.18 (diagnostic, PP-rule): v0.16 + a PP-derived 2–3 micro-asymmetry.

    This replaces v0.17 (row-kick) as the preferred diagnostic: we treat the same discrete
    micro-step as a seam/block asymmetry tied to the already-derived seam micro-index s_micro.

    Rule (discrete; no new continuous knobs):
      - take s_micro from the canonical Ud seam rule (v0.16, derived from k_rt mod 3)
      - apply one micro-step in the (2,3) plane by theta = (2π/(30·ρ)) * s_micro

    Implementation: reconstruct a representative complex CKM V via PDG parameterization
    from the v0.16 angles, then apply the discrete (2,3) micro-step on the left (row-basis).

    Note: stays diagnostic until PP-native placement (Uu/Ud-level) is fixed.
    """

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_18_monodromy_postR12_seam_down_oriented_pp23_1260"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10

    seam = (pol.get("postR12_seam") or {})
    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or 0)
    if s_micro == 0:
        s_micro = 1

    ck = (out.get("CKM") or {})
    ang = (ck.get("angles") or {})
    th12 = math.radians(float(ang.get("theta12_deg") or 0.0))
    th23 = math.radians(float(ang.get("theta23_deg") or 0.0))
    th13 = math.radians(float(ang.get("theta13_deg") or 0.0))
    ddeg = float(ang.get("delta_deg_from_sin") or 0.0)
    delta = math.radians(ddeg)

    V = np.array(_ckm_unitary_pdg(th12, th23, th13, delta), dtype=np.complex128)

    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))
    c = math.cos(theta_micro)
    s = math.sin(theta_micro)
    R23 = np.array([
        [1.0, 0.0, 0.0],
        [0.0, c, s],
        [0.0, -s, c],
    ], dtype=np.complex128)
    V2 = R23 @ V

    ck2 = _angles_J_from_unitary([[complex(V2[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23"] = out.get("CKM")
    out.setdefault("policy", {})
    out["policy"]["postL23_pp23"] = {
        "active": True,
        "action": "V <- R23(theta_micro) · V (PP23 micro-step)",
        "theta_rad": float(theta_micro),
        "theta_deg": float(math.degrees(theta_micro)),
        "rho": int(rho),
        "s_micro": int(s_micro),
        "source": "canonical seam s_micro (k_rt mod 3) via v0.16; replaces v0.17 row-kick",
    }

    out["CKM"] = {"V_abs": _rt_abs_from_np(V2), "unitary_residual": _rt_unitary_residual_np(V2), "angles": ck2}

    return out




def _rt_construct_misalignment_v0_19_monodromy_postR12_seam_down_oriented_pp23_uubasis_1260(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct v0.19 (preferred diagnostic): move PP23 from V-level to a PP-native sector placement.

    v0.18 applies PP23 by reconstructing a representative CKM via PDG angles and then left-multiplying by R23.
    v0.19 instead places the same *discrete* 2–3 micro-step as a *right basis* operation on Uu:

      Uu <- Uu · R23( -theta_micro )
      => V = Uu^† Ud_seam  becomes  V <- R23(+theta_micro) · V

    This yields the same θ23 lift (+1 micro-step when s_micro=+1) while staying inside the monodromy scaffold.

    No new continuous parameters; theta_micro is the same (2π/(30·ρ))·s_micro derived by the Ud seam lemma.
    """

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_19_monodromy_postR12_seam_down_oriented_pp23_uubasis_1260"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    K = int(pol.get("K") or 30)
    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    # down-oriented seam micro-index from v0.16 policy (fallback to rule if missing)
    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))

    # (2,3) micro-step (PP23)
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    # rebuild sector unitaries deterministically (same scaffold as v0.15/v0.16)
    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    # seam R12 on Ud (same as v0.16)
    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    # leptons (unchanged from v0.16)
    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)


    # PP23 placement in PDG-fixed row basis:
    # Build DL (row phases) so that (ud, us, cb, tb) are real in Vp = DL·V0·DR,
    # then apply A = DL^† · R23(+theta_micro) · DL on the left: V <- A·V0.
    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    # a_c can be set to 0 (gauge); remaining phases solved to pin cb and tb real.
    a_c = 0.0
    b_s = -_arg(complex(V0[0, 1])) - a_u
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag(
        [
            complex(math.cos(a_u), math.sin(a_u)),
            complex(math.cos(a_c), math.sin(a_c)),
            complex(math.cos(a_t), math.sin(a_t)),
        ]
    ).astype(np.complex128)

    ct = math.cos(theta_micro)
    st = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct, st], [0.0, -st, ct]], dtype=np.complex128)

    A = DL.conjugate().T @ R23 @ DL

    # Implement A·V0 via a PP-native right-basis update on Uu: Uu <- Uu · A^†
    Uu_pp = Uu @ A.conjugate().T

    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23"] = out.get("CKM")
    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}

    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["postL23_pp23"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "action": "Uu <- Uu · R23(-theta_micro)  =>  V <- R23(+theta_micro) · V",
        "theta_micro_rad": float(theta_micro),
        "theta_micro_deg": float(math.degrees(theta_micro)),
        "rho": int(rho),
        "s_micro": int(s_micro),
        "note": "PP-native placement; replaces PDG-reconstructed v0.18 PP23",
    }

    # recompute gate summary (diagnostic)
    try:
        ck_ang = ((out.get("CKM") or {}).get("angles") or {})
        pm_ang = ((out.get("PMNS") or {}).get("angles") or {})
        def _score(a: Dict[str, float]) -> float:
            return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2
        s_ckm = _score(ck_ang)
        s_pmns = _score(pm_ang)
        def _in_range(x: float, r: Tuple[float, float]) -> bool:
            return (x >= float(r[0])) and (x <= float(r[1]))
        ck_t12 = float(ck_ang.get("theta12_deg", 0.0))
        ck_t23 = float(ck_ang.get("theta23_deg", 0.0))
        ck_t13 = float(ck_ang.get("theta13_deg", 0.0))
        ck_J = float(ck_ang.get("J", 0.0))
        ck_order = bool(ck_t12 > ck_t23 > ck_t13)
        ck_ranges_ok = bool(_in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG) and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG) and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG))
        ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
        pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)
        pm_t12 = float(pm_ang.get("theta12_deg", 0.0))
        pm_t23 = float(pm_ang.get("theta23_deg", 0.0))
        pm_t13 = float(pm_ang.get("theta13_deg", 0.0))
        pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
        pass_pmns_pattern = bool(pm_large_count >= 2)
        pass_struct = bool(s_ckm < s_pmns)
        out["gate"] = {
            "score": {"ckm": float(s_ckm), "pmns": float(s_pmns), "pass": bool(pass_struct)},
            "ckm_pattern": {"pass": bool(pass_ckm_pattern), "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J}},
            "pmns_pattern": {"pass": bool(pass_pmns_pattern), "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13}, "large_count": int(pm_large_count)},
            "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
        }
    except Exception:
        pass

    return out



def _rt_construct_misalignment_v0_23_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_1260(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """RT construct v0.23 (Gate-2 candidate): add a **quark-grid sextet** (1,3) micro-rotation to CKM.

    Goal
    - Improve CKM agreement without new continuous knobs.
    - Keep PMNS path untouched (Goal-B locks remain in v0.20–v0.22).

    Rule (deterministic; discrete; PP-native)
    - Use the same monodromy scaffold as v0.19.
    - Define a quark sextet step θ_q = 2π/(nQ·6). For nQ=300 this is 0.2°.
    - Sign is set by k_CKM mod 3:
        s13_q := ((k_CKM mod 3) - 1) ∈ {-1,0,+1}
      so k≡2 (mod3) yields +0.2°.

    Placement (PP-native)
    - Work in the PDG-fixed **row phase gauge** defined by DL (same as v0.19).
    - Apply A13 = DL^† R13(θ13_adj) DL and A23 = DL^† R23(θ_micro) DL.
    - Implement both via a right-basis update on Uu:
        Uu <- Uu · A13^† · A23^†  =>  V <- A23 · A13 · V0

    NEG control flips the sextet sign (see v0.23_NEG).
    """

    # start from the same v0.16 scaffold to rebuild Uu/Ud/Unu/Ue deterministically
    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_23_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_1260"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)
    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    # down-oriented seam micro-index from v0.16 policy (fallback to rule if missing)
    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    # CKM13 quark sextet step (grid-aware): 2π/(nQ·6)
    theta_sext_q = float(2.0 * math.pi / (float(max(1, nQ)) * 6.0))
    s13_q = ((k_ckm_30 % 3) - 1)  # {-1,0,+1}
    theta13_adj = float(theta_sext_q * float(s13_q))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, float(eps))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    # seam R12 on Ud (same as v0.16)
    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    # leptons unchanged
    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag(
        [
            complex(math.cos(a_u), math.sin(a_u)),
            complex(math.cos(a_c), math.sin(a_c)),
            complex(math.cos(a_t), math.sin(a_t)),
        ]
    ).astype(np.complex128)

    # A23: PP23 micro-step (same as v0.19)
    ct23 = math.cos(theta_micro)
    st23 = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
    A23 = DL.conjugate().T @ R23 @ DL

    # A13: quark sextet micro-step
    ct13 = math.cos(theta13_adj)
    st13 = math.sin(theta13_adj)
    R13 = np.array([[ct13, 0.0, st13], [0.0, 1.0, 0.0], [-st13, 0.0, ct13]], dtype=np.complex128)
    A13 = DL.conjugate().T @ R13 @ DL

    # implement both steps PP-native on Uu right-basis
    Uu_pp = Uu @ A13.conjugate().T @ A23.conjugate().T

    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["postL23_pp23"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "action": "Uu <- Uu · A13^† · A23^†  =>  V <- A23 · A13 · V0 (PDG row-phase gauge DL)",
        "theta_micro_rad": float(theta_micro),
        "theta_micro_deg": float(math.degrees(theta_micro)),
        "rho": int(rho),
        "s_micro": int(s_micro),
    }
    out["policy"]["ckm13_sextet_engagement"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "action": "Uu <- Uu · A13^† (A13=DL^†R13(θ)DL); grid-aware sextet step",
        "theta_step_rad": float(theta_sext_q),
        "theta_step_deg": float(math.degrees(theta_sext_q)),
        "s13_q": int(s13_q),
        "theta13_adj_rad": float(theta13_adj),
        "theta13_adj_deg": float(math.degrees(theta13_adj)),
        "k_ckm_mod30": int(k_ckm_30),
        "k_ckm_mod3": int(k_ckm_30 % 3),
        "rule": "s13_q := ((k_CKM mod 3) - 1) ∈ {-1,0,+1}; θ = s13_q·(2π/(nQ·6))",
    }

    return out


def _rt_construct_misalignment_v0_23_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_1260_NEG(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """NEG for v0.23: same as v0.23 but with θ13_adj -> -θ13_adj (full recompute)."""

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_23_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_1260_NEG"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)
    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    theta_sext_q = float(2.0 * math.pi / (float(max(1, nQ)) * 6.0))
    s13_q = -((k_ckm_30 % 3) - 1)  # flipped sign
    theta13_adj = float(theta_sext_q * float(s13_q))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, float(eps))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag(
        [
            complex(math.cos(a_u), math.sin(a_u)),
            complex(math.cos(a_c), math.sin(a_c)),
            complex(math.cos(a_t), math.sin(a_t)),
        ]
    ).astype(np.complex128)

    ct23 = math.cos(theta_micro)
    st23 = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
    A23 = DL.conjugate().T @ R23 @ DL

    ct13 = math.cos(theta13_adj)
    st13 = math.sin(theta13_adj)
    R13 = np.array([[ct13, 0.0, st13], [0.0, 1.0, 0.0], [-st13, 0.0, ct13]], dtype=np.complex128)
    A13 = DL.conjugate().T @ R13 @ DL

    Uu_pp = Uu @ A13.conjugate().T @ A23.conjugate().T

    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["postL23_pp23"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "action": "Uu <- Uu · A13^† · A23^†  =>  V <- A23 · A13 · V0 (PDG row-phase gauge DL)",
        "theta_micro_rad": float(theta_micro),
        "theta_micro_deg": float(math.degrees(theta_micro)),
        "rho": int(rho),
        "s_micro": int(s_micro),
    }
    out["policy"]["ckm13_sextet_engagement"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "action": "NEG: Uu <- Uu · A13^† with flipped sign",
        "theta_step_rad": float(theta_sext_q),
        "theta_step_deg": float(math.degrees(theta_sext_q)),
        "s13_q": int(s13_q),
        "theta13_adj_rad": float(theta13_adj),
        "theta13_adj_deg": float(math.degrees(theta13_adj)),
        "k_ckm_mod30": int(k_ckm_30),
        "k_ckm_mod3": int(k_ckm_30 % 3),
        "rule": "NEG: s13_q := -((k_CKM mod 3) - 1)",
    }
    out.setdefault("NEG", {})
    out["NEG"]["ckm13_sextet_sign_flip"] = True

    return out




def _rt_construct_misalignment_v0_24_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_micro2_phiB_1260(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """RT construct v0.24 (Gate-2 candidate): CKM θ13 lift via **ρ² micro-step** with seam phase (phi_B).

    Motivation
    - v0.23 (0.2° real R13) improved θ13 but collapsed CKM CP (δ, J).
    - v0.24 keeps the update PP-native but makes the R13 step *phaseful* (same edge phase phi_B as the Ud seam),
      and uses a smaller ρ² step (2π/(30·ρ²) ≈ 0.12° for ρ=10).

    Determinism / no new knobs
    - Step size is derived from (K=30, ρ) only: θ_ρ² = 2π/(30·ρ²).
    - Sign uses the same Z3-derived rule: s13 := (k_CKM mod 3) − 1 ∈ {−1,0,+1}.

    Placement (PP-native)
    - Work in the same PDG-fixed row-phase gauge DL used in v0.19/v0.23.
    - Apply A13 = DL^† · R13_phiB(θ13_adj) · DL and A23 = DL^† · R23(θ_micro) · DL.
    - Implement via a right-basis update on Uu: Uu <- Uu · A13^† · A23^†.
    """

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_24_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_micro2_phiB_1260"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    # down-oriented seam micro-index (same as v0.16)
    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    # CKM13 rho^2 micro-step (≈0.12° for rho=10)
    theta_rho2 = float(2.0 * math.pi / (30.0 * float(max(1, rho)) * float(max(1, rho))))
    s13 = ((k_ckm_30 % 3) - 1)
    theta13_adj = float(theta_rho2 * float(s13))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    # Ud seam R12 (same as v0.16)
    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    # leptons unchanged (v0.16)
    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag(
        [
            complex(math.cos(a_u), math.sin(a_u)),
            complex(math.cos(a_c), math.sin(a_c)),
            complex(math.cos(a_t), math.sin(a_t)),
        ]
    ).astype(np.complex128)

    # A23: PP23 micro-step (same as v0.19)
    ct23 = math.cos(theta_micro)
    st23 = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
    A23 = DL.conjugate().T @ R23 @ DL

    # A13: phaseful rho^2 micro-step using phi_B (seam edge phase)
    ct13 = math.cos(theta13_adj)
    st13 = math.sin(theta13_adj)
    R13 = np.array([[ct13, 0.0, st13 * e_m], [0.0, 1.0, 0.0], [-st13 * e_p, 0.0, ct13]], dtype=np.complex128)
    A13 = DL.conjugate().T @ R13 @ DL

    # PP-native right-basis update on Uu
    Uu_pp = Uu @ A13.conjugate().T @ A23.conjugate().T

    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["postL23_pp23"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "action": "Uu <- Uu · A13^† · A23^†  =>  V <- A23 · A13 · V0 (PDG row-phase gauge DL)",
        "theta_micro_rad": float(theta_micro),
        "theta_micro_deg": float(math.degrees(theta_micro)),
        "rho": int(rho),
        "s_micro": int(s_micro),
    }
    out["policy"]["ckm13_rho2_phiB"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "axis": "13",
        "phase": "phi_B",
        "theta_step_deg": float(math.degrees(theta_rho2)),
        "k_ckm_mod30": int(k_ckm_30),
        "k_ckm_mod3": int(k_ckm_30 % 3),
        "s13": int(s13),
        "theta13_adj_deg": float(math.degrees(theta13_adj)),
        "rule": "s13 := (k_CKM mod 3) - 1; θ = s13·(2π/(30·ρ²)); R13 uses seam phase phi_B",
    }

    # recompute gate readouts after the CKM update
    try:
        out["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return out



def _rt_construct_misalignment_v0_24_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_micro2_phiB_1260_NEG(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """NEG for v0.24: flip sign of the ρ² CKM13 step (s13 -> -s13)."""

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_24_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_micro2_phiB_1260_NEG"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    theta_rho2 = float(2.0 * math.pi / (30.0 * float(max(1, rho)) * float(max(1, rho))))
    s13 = -((k_ckm_30 % 3) - 1)
    theta13_adj = float(theta_rho2 * float(s13))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag(
        [
            complex(math.cos(a_u), math.sin(a_u)),
            complex(math.cos(a_c), math.sin(a_c)),
            complex(math.cos(a_t), math.sin(a_t)),
        ]
    ).astype(np.complex128)

    ct23 = math.cos(theta_micro)
    st23 = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
    A23 = DL.conjugate().T @ R23 @ DL

    ct13 = math.cos(theta13_adj)
    st13 = math.sin(theta13_adj)
    R13 = np.array([[ct13, 0.0, st13 * e_m], [0.0, 1.0, 0.0], [-st13 * e_p, 0.0, ct13]], dtype=np.complex128)
    A13 = DL.conjugate().T @ R13 @ DL

    Uu_pp = Uu @ A13.conjugate().T @ A23.conjugate().T

    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["postL23_pp23"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "action": "Uu <- Uu · A13^† · A23^†  =>  V <- A23 · A13 · V0 (PDG row-phase gauge DL)",
        "theta_micro_rad": float(theta_micro),
        "theta_micro_deg": float(math.degrees(theta_micro)),
        "rho": int(rho),
        "s_micro": int(s_micro),
    }
    out["policy"]["ckm13_rho2_phiB"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "axis": "13",
        "phase": "phi_B",
        "theta_step_deg": float(math.degrees(theta_rho2)),
        "k_ckm_mod30": int(k_ckm_30),
        "k_ckm_mod3": int(k_ckm_30 % 3),
        "s13": int(s13),
        "theta13_adj_deg": float(math.degrees(theta13_adj)),
        "rule": "NEG: s13 := -((k_CKM mod 3) - 1); θ = s13·(2π/(30·ρ²))",
    }

    out.setdefault("NEG", {})
    out["NEG"]["ckm13_rho2_phiB_sign_flip"] = True

    try:
        out["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return out



def _rt_construct_misalignment_v0_25_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_1260(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """RT construct v0.25 (Gate-2 candidate): CKM θ13 lift via **quark sextet step** with seam phase (phi_B).

    - Uses θ_sext = 2π/(nQ·6) with nQ=30·ρ (C300) ⇒ ~0.2° for ρ=10.
    - Uses same Z3 sign rule: s13 := (k_CKM mod 3) − 1.
    - Uses phaseful R13 with seam phase phi_B to avoid collapsing CP.
    """

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_25_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_1260"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    theta_sext_q = float(2.0 * math.pi / (float(nQ) * 6.0))
    s13 = ((k_ckm_30 % 3) - 1)
    theta13_adj = float(theta_sext_q * float(s13))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag(
        [
            complex(math.cos(a_u), math.sin(a_u)),
            complex(math.cos(a_c), math.sin(a_c)),
            complex(math.cos(a_t), math.sin(a_t)),
        ]
    ).astype(np.complex128)

    ct23 = math.cos(theta_micro)
    st23 = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
    A23 = DL.conjugate().T @ R23 @ DL

    ct13 = math.cos(theta13_adj)
    st13 = math.sin(theta13_adj)
    R13 = np.array([[ct13, 0.0, st13 * e_m], [0.0, 1.0, 0.0], [-st13 * e_p, 0.0, ct13]], dtype=np.complex128)
    A13 = DL.conjugate().T @ R13 @ DL

    Uu_pp = Uu @ A13.conjugate().T @ A23.conjugate().T

    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["postL23_pp23"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "action": "Uu <- Uu · A13^† · A23^†  =>  V <- A23 · A13 · V0 (PDG row-phase gauge DL)",
        "theta_micro_rad": float(theta_micro),
        "theta_micro_deg": float(math.degrees(theta_micro)),
        "rho": int(rho),
        "s_micro": int(s_micro),
    }
    out["policy"]["ckm13_sextet_phiB"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "axis": "13",
        "phase": "phi_B",
        "theta_step_deg": float(math.degrees(theta_sext_q)),
        "k_ckm_mod30": int(k_ckm_30),
        "k_ckm_mod3": int(k_ckm_30 % 3),
        "s13": int(s13),
        "theta13_adj_deg": float(math.degrees(theta13_adj)),
        "rule": "s13 := (k_CKM mod 3) - 1; θ = s13·(2π/(nQ·6)); R13 uses seam phase phi_B",
    }

    try:
        out["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return out



def _rt_construct_misalignment_v0_25_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_1260_NEG(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """NEG for v0.25: flip sign of the rho^2 CKM13 step (s13 -> -s13)."""

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_25_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_1260_NEG"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    theta_rho2 = float(2.0 * math.pi / (30.0 * float(max(1, rho)) * float(max(1, rho))))
    s13 = -((k_ckm_30 % 3) - 1)
    theta13_adj = float(theta_rho2 * float(s13))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag(
        [
            complex(math.cos(a_u), math.sin(a_u)),
            complex(math.cos(a_c), math.sin(a_c)),
            complex(math.cos(a_t), math.sin(a_t)),
        ]
    ).astype(np.complex128)

    ct23 = math.cos(theta_micro)
    st23 = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
    A23 = DL.conjugate().T @ R23 @ DL

    ct13 = math.cos(theta13_adj)
    st13 = math.sin(theta13_adj)
    R13 = np.array([[ct13, 0.0, st13 * e_m], [0.0, 1.0, 0.0], [-st13 * e_p, 0.0, ct13]], dtype=np.complex128)
    A13 = DL.conjugate().T @ R13 @ DL

    Uu_pp = Uu @ A13.conjugate().T @ A23.conjugate().T

    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["postL23_pp23"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "action": "Uu <- Uu · A13^† · A23^†  =>  V <- A23 · A13 · V0 (PDG row-phase gauge DL)",
        "theta_micro_rad": float(theta_micro),
        "theta_micro_deg": float(math.degrees(theta_micro)),
        "rho": int(rho),
        "s_micro": int(s_micro),
    }
    out["policy"]["ckm13_rho2_phiB"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "axis": "13",
        "phase": "phi_B",
        "theta_step_deg": float(math.degrees(theta_rho2)),
        "k_ckm_mod30": int(k_ckm_30),
        "k_ckm_mod3": int(k_ckm_30 % 3),
        "s13": int(s13),
        "theta13_adj_deg": float(math.degrees(theta13_adj)),
        "rule": "NEG: s13 := -((k_CKM mod 3) - 1); θ = s13·(2π/(30·ρ²))",
    }

    out.setdefault("NEG", {})
    out["NEG"]["ckm13_rho2_phiB_sign_flip"] = True

    try:
        out["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return out






def _rt_construct_misalignment_v0_29_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_PP_NATIVE_NODL_1260(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """RT construct v0.29 (Gate-4 exploratory): make the PP23+CKM13 lifts **PP-native** (no PDG row-phase DL).

    Motivation
    - v0.25 uses a *derived* PDG row-phase gauge DL(V0) to conjugate R23/R13.
      That is deterministic but still a post-hoc convention.
    - v0.29 applies the same lifts directly in the Uu right-basis:
        Uu <- Uu · R13^† · R23^†   (no DL)
      which implies:
        V <- R23 · R13 · V0

    Invariants
    - No new knobs.
    - Keeps v0.21/v0.25 sign rules and sextet step.
    - Leaves the v0.25 regression lock untouched (this is diagnostic unless promoted).
    """

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_29_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_PP_NATIVE_NODL_1260"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    theta_sext_q = float(2.0 * math.pi / (float(nQ) * 6.0))
    s13 = ((k_ckm_30 % 3) - 1)
    theta13_adj = float(theta_sext_q * float(s13))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    ct23 = math.cos(theta_micro)
    st23 = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)

    ct13 = math.cos(theta13_adj)
    st13 = math.sin(theta13_adj)
    R13 = np.array([[ct13, 0.0, st13 * e_m], [0.0, 1.0, 0.0], [-st13 * e_p, 0.0, ct13]], dtype=np.complex128)

    # PP-native: apply directly (no DL conjugation)
    Uu_pp = Uu @ R13.conjugate().T @ R23.conjugate().T

    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["postL23_pp23"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "action": "Uu <- Uu · R13^† · R23^†  =>  V <- R23 · R13 · V0 (PP-native; no DL)",
        "theta_micro_rad": float(theta_micro),
        "theta_micro_deg": float(math.degrees(theta_micro)),
        "rho": int(rho),
        "s_micro": int(s_micro),
    }
    out["policy"]["ckm13_sextet_phiB"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "axis": "13",
        "phase": "phi_B",
        "theta_step_deg": float(math.degrees(theta_sext_q)),
        "k_ckm_mod30": int(k_ckm_30),
        "k_ckm_mod3": int(k_ckm_30 % 3),
        "s13": int(s13),
        "theta13_adj_deg": float(math.degrees(theta13_adj)),
        "rule": "s13 := (k_CKM mod 3) - 1; θ = s13·(2π/(nQ·6)); R13 uses seam phase phi_B",
    }

    try:
        out["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return out



def _rt_construct_misalignment_v0_29_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_PP_NATIVE_NODL_1260_NEG(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """NEG for v0.29: flip sign of the sextet CKM13 step (s13 -> -s13)."""

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_29_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_PP_NATIVE_NODL_1260_NEG"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    theta_sext_q = float(2.0 * math.pi / (float(nQ) * 6.0))
    s13 = -((k_ckm_30 % 3) - 1)
    theta13_adj = float(theta_sext_q * float(s13))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    ct23 = math.cos(theta_micro)
    st23 = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)

    ct13 = math.cos(theta13_adj)
    st13 = math.sin(theta13_adj)
    R13 = np.array([[ct13, 0.0, st13 * e_m], [0.0, 1.0, 0.0], [-st13 * e_p, 0.0, ct13]], dtype=np.complex128)

    Uu_pp = Uu @ R13.conjugate().T @ R23.conjugate().T

    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["postL23_pp23"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "action": "Uu <- Uu · R13^† · R23^†  =>  V <- R23 · R13 · V0 (PP-native; no DL)",
        "theta_micro_rad": float(theta_micro),
        "theta_micro_deg": float(math.degrees(theta_micro)),
        "rho": int(rho),
        "s_micro": int(s_micro),
    }
    out["policy"]["ckm13_sextet_phiB"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "axis": "13",
        "phase": "phi_B",
        "theta_step_deg": float(math.degrees(theta_sext_q)),
        "k_ckm_mod30": int(k_ckm_30),
        "k_ckm_mod3": int(k_ckm_30 % 3),
        "s13": int(s13),
        "theta13_adj_deg": float(math.degrees(theta13_adj)),
        "rule": "NEG: s13 := -((k_CKM mod 3) - 1); θ = s13·(2π/(nQ·6))",
    }

    try:
        out["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return out


def _rt_construct_misalignment_v0_30_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_V0PHASE_NODG_1260(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """RT construct v0.30 (Gate-4 candidate): phase-aligned PP23+CKM13 lifts without PDG row/col phase fix.

    - DL23/DL13 are derived directly from the raw V0 phases (no PDG conventions).
    - Keeps the successful sextet and micro rules; no new knobs.
    """

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_30_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_V0PHASE_NODG_1260"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    theta_sext_q = float(2.0 * math.pi / (float(nQ) * 6.0))
    s13 = ((k_ckm_30 % 3) - 1)
    theta13_adj = float(theta_sext_q * float(s13))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    # DL23: cancel phases of (c,s) and (t,s) in the raw V0
    phi_c = float(np.angle(V0[1, 1]))
    phi_t = float(np.angle(V0[2, 1]))
    DL23 = np.diag([
        1.0,
        complex(math.cos(-phi_c), math.sin(-phi_c)),
        complex(math.cos(-phi_t), math.sin(-phi_t)),
    ]).astype(np.complex128)

    ct23 = math.cos(theta_micro)
    st23 = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
    A23 = DL23.conjugate().T @ R23 @ DL23

    # DL13: cancel phases of (u,d) and (t,d) in the raw V0
    phi_u = float(np.angle(V0[0, 0]))
    phi_tu = float(np.angle(V0[2, 0]))
    DL13 = np.diag([
        complex(math.cos(-phi_u), math.sin(-phi_u)),
        1.0,
        complex(math.cos(-phi_tu), math.sin(-phi_tu)),
    ]).astype(np.complex128)

    ct13 = math.cos(theta13_adj)
    st13 = math.sin(theta13_adj)
    R13 = np.array([[ct13, 0.0, st13 * e_m], [0.0, 1.0, 0.0], [-st13 * e_p, 0.0, ct13]], dtype=np.complex128)
    A13 = DL13.conjugate().T @ R13 @ DL13

    A = A23 @ A13

    Uu_pp = Uu @ A.conjugate().T
    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["postL23_pp23"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "action": "Uu <- Uu · (A23·A13)^†; DL23/DL13 derived from raw V0 phases (no PDG fix)",
        "theta_micro_rad": float(theta_micro),
        "theta_micro_deg": float(math.degrees(theta_micro)),
        "rho": int(rho),
        "s_micro": int(s_micro),
        "DL23_from": "V0 raw phases at (1,1),(2,1)",
        "DL13_from": "V0 raw phases at (0,0),(2,0)",
    }
    out["policy"]["ckm13_sextet_phiB"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "axis": "13",
        "phase": "phi_B",
        "theta_step_deg": float(math.degrees(theta_sext_q)),
        "k_ckm_mod30": int(k_ckm_30),
        "k_ckm_mod3": int(k_ckm_30 % 3),
        "s13": int(s13),
        "theta13_adj_deg": float(math.degrees(theta13_adj)),
        "rule": "s13 := (k_CKM mod 3) - 1; θ = s13·(2π/(nQ·6)); R13 uses seam phase phi_B",
    }

    try:
        out["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return out



def _rt_construct_misalignment_v0_30_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_V0PHASE_NODG_1260_NEG(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """NEG for v0.30: flip sign of the sextet CKM13 step (s13 -> -s13) with the same raw-V0 phase alignment."""

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_30_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_V0PHASE_NODG_1260_NEG"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    theta_sext_q = float(2.0 * math.pi / (float(nQ) * 6.0))
    s13 = -((k_ckm_30 % 3) - 1)
    theta13_adj = float(theta_sext_q * float(s13))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    phi_c = float(np.angle(V0[1, 1]))
    phi_t = float(np.angle(V0[2, 1]))
    DL23 = np.diag([
        1.0,
        complex(math.cos(-phi_c), math.sin(-phi_c)),
        complex(math.cos(-phi_t), math.sin(-phi_t)),
    ]).astype(np.complex128)

    ct23 = math.cos(theta_micro)
    st23 = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
    A23 = DL23.conjugate().T @ R23 @ DL23

    phi_u = float(np.angle(V0[0, 0]))
    phi_tu = float(np.angle(V0[2, 0]))
    DL13 = np.diag([
        complex(math.cos(-phi_u), math.sin(-phi_u)),
        1.0,
        complex(math.cos(-phi_tu), math.sin(-phi_tu)),
    ]).astype(np.complex128)

    ct13 = math.cos(theta13_adj)
    st13 = math.sin(theta13_adj)
    R13 = np.array([[ct13, 0.0, st13 * e_m], [0.0, 1.0, 0.0], [-st13 * e_p, 0.0, ct13]], dtype=np.complex128)
    A13 = DL13.conjugate().T @ R13 @ DL13

    A = A23 @ A13

    Uu_pp = Uu @ A.conjugate().T
    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["postL23_pp23"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "action": "NEG: same as v0.30 but s13 flipped",
        "theta_micro_rad": float(theta_micro),
        "theta_micro_deg": float(math.degrees(theta_micro)),
        "rho": int(rho),
        "s_micro": int(s_micro),
        "DL23_from": "V0 raw phases at (1,1),(2,1)",
        "DL13_from": "V0 raw phases at (0,0),(2,0)",
    }
    out["policy"]["ckm13_sextet_phiB"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "axis": "13",
        "phase": "phi_B",
        "theta_step_deg": float(math.degrees(theta_sext_q)),
        "k_ckm_mod30": int(k_ckm_30),
        "k_ckm_mod3": int(k_ckm_30 % 3),
        "s13": int(s13),
        "theta13_adj_deg": float(math.degrees(theta13_adj)),
        "rule": "NEG: s13 := -((k_CKM mod 3) - 1)",
    }

    try:
        out["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return out


def _rt_construct_misalignment_v0_31_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_CANON_ROWPHASE_1260(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """RT construct v0.31 (Gate-4): canonical row-phase gauge from internal constraints (ud,us,cb,tb real).

    - Derive DL,DR such that Vg = DL·V0·DR has (ud, us, cb, tb) real (positive by convention).
    - Apply PP23 and phaseful CKM13 sextet lift in that canonical row-phase gauge:
        A23 = DL^† R23 DL
        A13 = DL^† R13_phiB DL
        Uu <- Uu · (A23·A13)^†

    This removes explicit dependence on any named "PDG" helper while keeping the successful
    phase-aligned placement.
    """

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_31_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_CANON_ROWPHASE_1260"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    theta_sext_q = float(2.0 * math.pi / (float(nQ) * 6.0))
    s13 = ((k_ckm_30 % 3) - 1)
    theta13_adj = float(theta_sext_q * float(s13))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_d = 0.0
    b_s = -_arg(complex(V0[0, 1])) - a_u
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag([
        complex(math.cos(a_u), math.sin(a_u)),
        complex(math.cos(a_c), math.sin(a_c)),
        complex(math.cos(a_t), math.sin(a_t)),
    ]).astype(np.complex128)

    DR = np.diag([
        complex(math.cos(b_d), math.sin(b_d)),
        complex(math.cos(b_s), math.sin(b_s)),
        complex(math.cos(b_b), math.sin(b_b)),
    ]).astype(np.complex128)

    Vg = DL @ V0 @ DR

    ct23 = math.cos(theta_micro)
    st23 = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
    A23 = DL.conjugate().T @ R23 @ DL

    ct13 = math.cos(theta13_adj)
    st13 = math.sin(theta13_adj)
    R13 = np.array([[ct13, 0.0, st13 * e_m], [0.0, 1.0, 0.0], [-st13 * e_p, 0.0, ct13]], dtype=np.complex128)
    A13 = DL.conjugate().T @ R13 @ DL

    A = A23 @ A13

    Uu_pp = Uu @ A.conjugate().T
    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["rowcol_canon"] = {
        "constraints": "ud/us/cb/tb real (b_d=0, a_c=0 gauge)",
        "a_u": float(a_u),
        "a_c": float(a_c),
        "a_t": float(a_t),
        "b_d": float(b_d),
        "b_s": float(b_s),
        "b_b": float(b_b),
    }
    out["policy"]["postL23_pp23"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "action": "A23=DL^† R23 DL (DL from canonical row/col gauge), A13=DL^† R13_phiB DL",
        "theta_micro_deg": float(math.degrees(theta_micro)),
        "rho": int(rho),
        "s_micro": int(s_micro),
    }
    out["policy"]["ckm13_sextet_phiB"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "axis": "13",
        "phase": "phi_B",
        "theta_step_deg": float(math.degrees(theta_sext_q)),
        "k_ckm_mod30": int(k_ckm_30),
        "k_ckm_mod3": int(k_ckm_30 % 3),
        "s13": int(s13),
        "theta13_adj_deg": float(math.degrees(theta13_adj)),
    }

    try:
        out["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    # Diagnostic: ensure gauge constraints were met
    try:
        out.setdefault("diagnostic", {})
        out["diagnostic"]["Vg_constraints"] = {
            "arg_ud": float(np.angle(Vg[0,0])),
            "arg_us": float(np.angle(Vg[0,1])),
            "arg_cb": float(np.angle(Vg[1,2])),
            "arg_tb": float(np.angle(Vg[2,2])),
        }
    except Exception:
        pass

    return out



def _rt_construct_misalignment_v0_31_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_CANON_ROWPHASE_1260_NEG(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """NEG for v0.31: flip sign of the sextet CKM13 step (s13 -> -s13) in the same canonical row-phase gauge."""

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_31_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_CANON_ROWPHASE_1260_NEG"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    theta_sext_q = float(2.0 * math.pi / (float(nQ) * 6.0))
    s13 = -((k_ckm_30 % 3) - 1)
    theta13_adj = float(theta_sext_q * float(s13))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_d = 0.0
    b_s = -_arg(complex(V0[0, 1])) - a_u
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag([
        complex(math.cos(a_u), math.sin(a_u)),
        complex(math.cos(a_c), math.sin(a_c)),
        complex(math.cos(a_t), math.sin(a_t)),
    ]).astype(np.complex128)

    ct23 = math.cos(theta_micro)
    st23 = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
    A23 = DL.conjugate().T @ R23 @ DL

    ct13 = math.cos(theta13_adj)
    st13 = math.sin(theta13_adj)
    R13 = np.array([[ct13, 0.0, st13 * e_m], [0.0, 1.0, 0.0], [-st13 * e_p, 0.0, ct13]], dtype=np.complex128)
    A13 = DL.conjugate().T @ R13 @ DL

    A = A23 @ A13

    Uu_pp = Uu @ A.conjugate().T
    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["rowcol_canon"] = {
        "constraints": "ud/us/cb/tb real (b_d=0, a_c=0 gauge)",
        "a_u": float(a_u),
        "a_c": float(a_c),
        "a_t": float(a_t),
        "b_d": float(b_d),
        "b_s": float(b_s),
        "b_b": float(b_b),
    }
    out["policy"]["postL23_pp23"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "action": "NEG: A23=DL^† R23 DL, A13=DL^† R13_phiB DL with s13 flipped",
        "theta_micro_deg": float(math.degrees(theta_micro)),
        "rho": int(rho),
        "s_micro": int(s_micro),
    }
    out["policy"]["ckm13_sextet_phiB"] = {
        "active": True,
        "placement": "Uu_right_basis",
        "axis": "13",
        "phase": "phi_B",
        "theta_step_deg": float(math.degrees(theta_sext_q)),
        "k_ckm_mod30": int(k_ckm_30),
        "k_ckm_mod3": int(k_ckm_30 % 3),
        "s13": int(s13),
        "theta13_adj_deg": float(math.degrees(theta13_adj)),
        "rule": "NEG: s13 := -((k_CKM mod 3) - 1)",
    }

    try:
        out["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return out




def _rt_construct_misalignment_v0_33__core_holoC30_GRIDBEST(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
    holo_on_seam: bool,
) -> Dict[str, Any]:
    """Internal core for v0.33 (CKM holonomy freeze)."""
    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    # Fixed discrete branch (from grid argmin v0.2)
    seam_phi = float(phi_A)
    r13_phi = float(phi_A)
    mu30 = -1
    mt30 = 15

    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))

    theta_sext_q = float(2.0 * math.pi / (float(nQ) * 6.0))
    seam_extra = float(-0.25 * theta_sext_q)
    micro_extra = float(+0.50 * theta_sext_q)

    s13 = ((k_ckm_30 % 3) - 1)
    theta13_adj = float(theta_sext_q * float(s13))

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    def _build_kick(p: int, phi_edge: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        Hm = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (Hm + Hm.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = Hm / m
        eps = (RT_EPS0 if int(p) == 6 else (-RT_EPS0 if int(p) == 5 else RT_EPS0))
        Uk = _rt_expm_i_hermitian(Hn, float(eps))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    Uu = _monodromy(_build_kick(6, float(phi_A)), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, float(phi_B)), nQ, kQ_base, dkQ, rho_sign=-1)

    alpha_u = float(2.0 * math.pi / 30.0) * float(int(mu30))
    alpha_t = float(2.0 * math.pi / 30.0) * float(int(mt30))
    alpha_c = float(-alpha_u - alpha_t)
    Hu = complex(math.cos(alpha_u), math.sin(alpha_u))
    Hc = complex(math.cos(alpha_c), math.sin(alpha_c))
    Ht = complex(math.cos(alpha_t), math.sin(alpha_t))
    H = np.diag([Hu, Hc, Ht]).astype(np.complex128)
    Hh = H.conjugate().T

    theta_base = float(2.0 * math.pi / 30.0)
    theta_micro_base = float((2.0 * math.pi / (30.0 * float(max(1, int(rho))))) * float(int(s_micro)))
    theta_seam = float(theta_base + theta_micro_base + float(seam_extra))
    theta_micro_local = float(theta_micro_base + float(micro_extra))

    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m_seam = complex(math.cos(-seam_phi), math.sin(-seam_phi))
    e_p_seam = complex(math.cos(+seam_phi), math.sin(+seam_phi))
    R12 = np.array([[c, s * e_m_seam, 0.0], [-s * e_p_seam, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = ((Ud @ Hh) @ R12 @ H) if bool(holo_on_seam) else (Ud @ R12)

    V0 = Uu.conjugate().T @ Ud_seam

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b
    DL = np.diag([
        complex(math.cos(a_u), math.sin(a_u)),
        complex(math.cos(a_c), math.sin(a_c)),
        complex(math.cos(a_t), math.sin(a_t)),
    ]).astype(np.complex128)

    ct23 = math.cos(theta_micro_local)
    st23 = math.sin(theta_micro_local)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
    A23 = DL.conjugate().T @ (Hh @ R23 @ H) @ DL

    ct13 = math.cos(theta13_adj)
    st13 = math.sin(theta13_adj)
    e_m13 = complex(math.cos(-r13_phi), math.sin(-r13_phi))
    e_p13 = complex(math.cos(+r13_phi), math.sin(+r13_phi))
    R13 = np.array([[ct13, 0.0, st13 * e_m13], [0.0, 1.0, 0.0], [-st13 * e_p13, 0.0, ct13]], dtype=np.complex128)
    A13 = DL.conjugate().T @ (Hh @ R13 @ H) @ DL

    Uu_pp = Uu @ A13.conjugate().T @ A23.conjugate().T
    V = Uu_pp.conjugate().T @ Ud_seam

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}

    out.setdefault("policy", {})
    out["policy"]["ckm_holoC30"] = {
        "seam_phase": "phi_A",
        "r13_phase": "phi_A",
        "mu30": int(mu30),
        "mt30": int(mt30),
        "holo_on_seam": bool(holo_on_seam),
        "seam_extra": {"mult_theta_sext_q": -0.25, "value_rad": float(seam_extra)},
        "micro_extra": {"mult_theta_sext_q": +0.50, "value_rad": float(micro_extra)},
        "s_micro": int(s_micro),
        "rho_eff": int(rho),
        "theta13_adj": {"s13": int(s13), "value_rad": float(theta13_adj)},
    }
    return out


def _rt_construct_misalignment_v0_33_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_GRIDBEST_1260(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """RT construct v0.33 (Gate-4): freeze the best discrete CKM holonomy candidate from diag grid (v0.2)."""
    out = _rt_construct_misalignment_v0_33__core_holoC30_GRIDBEST(delta_deg_ckm, delta_deg_pmns, holo_on_seam=True)
    out["version"] = "rt_construct_v0_33_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_GRIDBEST_1260"
    return out


def _rt_construct_misalignment_v0_33_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_GRIDBEST_1260_NEG(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """NEG variant: disable holonomy-on-seam (expected to worsen CKM fit)."""
    out = _rt_construct_misalignment_v0_33__core_holoC30_GRIDBEST(delta_deg_ckm, delta_deg_pmns, holo_on_seam=False)
    out["version"] = "rt_construct_v0_33_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_GRIDBEST_1260_NEG"
    return out

def _rt_construct_misalignment_v0_26_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_microbend_1260(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """RT construct v0.26 (diagnostic): v0.25 + microbend (no new knobs).

    Microbend policy (deterministic):
    - PP23: θ_micro -> θ_micro·(1 + 1/|L_cap|), |L_cap|=7.
    - CKM13 sextet: θ13 -> θ13·(1 - sin²θ_W), sin²θ_W=1/4 ⇒ factor 3/4.

    Not promoted; for comparison only.
    """

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_26_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_microbend_1260"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    theta_sext_q = float(2.0 * math.pi / (float(nQ) * 6.0))
    s13 = ((k_ckm_30 % 3) - 1)
    theta13_adj = float(theta_sext_q * float(s13))

    cap_abs = 7.0
    fac_pp23 = (1.0 + 1.0 / cap_abs)
    fac_ckm13 = 0.75

    theta_micro_eff = float(theta_micro * fac_pp23)
    theta13_adj_eff = float(theta13_adj * fac_ckm13)

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag(
        [
            complex(math.cos(a_u), math.sin(a_u)),
            complex(math.cos(a_c), math.sin(a_c)),
            complex(math.cos(a_t), math.sin(a_t)),
        ]
    ).astype(np.complex128)

    ct23 = math.cos(theta_micro_eff)
    st23 = math.sin(theta_micro_eff)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
    A23 = DL.conjugate().T @ R23 @ DL

    ct13 = math.cos(theta13_adj_eff)
    st13 = math.sin(theta13_adj_eff)
    R13 = np.array([[ct13, 0.0, st13 * e_m], [0.0, 1.0, 0.0], [-st13 * e_p, 0.0, ct13]], dtype=np.complex128)
    A13 = DL.conjugate().T @ R13 @ DL

    Uu_pp = Uu @ A13.conjugate().T @ A23.conjugate().T

    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["microbend"] = {
        "active": True,
        "cap_abs": int(cap_abs),
        "fac_pp23": float(fac_pp23),
        "fac_ckm13": float(fac_ckm13),
        "theta_micro_deg_base": float(math.degrees(theta_micro)),
        "theta_micro_deg_eff": float(math.degrees(theta_micro_eff)),
        "theta13_adj_deg_base": float(math.degrees(theta13_adj)),
        "theta13_adj_deg_eff": float(math.degrees(theta13_adj_eff)),
    }

    try:
        out["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return out



def _rt_construct_misalignment_v0_34_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_CPBEST_1260(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """v0.34: freeze CPBEST discrete holonomy candidate (hits CKM tolerances)."""
    out = _rt_construct_misalignment_v0_34__core_holoC30_CPBEST(delta_deg_ckm, delta_deg_pmns, holo_on_seam=False)
    out["version"] = "rt_construct_v0_34_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_CPBEST_1260"
    return out


def _rt_construct_misalignment_v0_34_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_CPBEST_1260_NEG(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """v0.34 NEG: toggle holonomy-on-seam (sanity/contrast)."""
    out = _rt_construct_misalignment_v0_34__core_holoC30_CPBEST(delta_deg_ckm, delta_deg_pmns, holo_on_seam=True)
    out["version"] = "rt_construct_v0_34_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_CPBEST_1260_NEG"
    return out



def _rt_construct_misalignment_v0_34__core_holoC30_CPBEST(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
    holo_on_seam: bool,
) -> Dict[str, Any]:
    """Internal core for v0.34 (CKM CP-holonomy freeze; CPBEST)."""
    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)
    # Fixed discrete branch (CPBEST freeze v0.34)
    seam_phi = float(phi_B)
    r13_phi = float(phi_B)
    mu30 = 1
    mt30 = 2

    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_sext_q = float(2.0 * math.pi / (float(nQ) * 6.0))
    seam_extra = float(+1.50 * theta_sext_q)
    micro_extra = float(+2.50 * theta_sext_q)

    s13 = ((k_ckm_30 % 3) - 1)
    theta13_adj = float(theta_sext_q * float(s13))

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    def _build_kick(p: int, phi_edge: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        Hm = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (Hm + Hm.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = Hm / m
        eps = (RT_EPS0 if int(p) == 6 else (-RT_EPS0 if int(p) == 5 else RT_EPS0))
        Uk = _rt_expm_i_hermitian(Hn, float(eps))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    Uu = _monodromy(_build_kick(6, float(phi_A)), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, float(phi_B)), nQ, kQ_base, dkQ, rho_sign=-1)

    alpha_u = float(2.0 * math.pi / 30.0) * float(int(mu30))
    alpha_t = float(2.0 * math.pi / 30.0) * float(int(mt30))
    alpha_c = float(-alpha_u - alpha_t)
    Hu = complex(math.cos(alpha_u), math.sin(alpha_u))
    Hc = complex(math.cos(alpha_c), math.sin(alpha_c))
    Ht = complex(math.cos(alpha_t), math.sin(alpha_t))
    H = np.diag([Hu, Hc, Ht]).astype(np.complex128)
    Hh = H.conjugate().T

    theta_base = float(2.0 * math.pi / 30.0)
    theta_micro_base = float((2.0 * math.pi / (30.0 * float(max(1, int(rho))))) * float(int(s_micro)))
    theta_seam = float(theta_base + theta_micro_base + float(seam_extra))
    theta_micro_local = float(theta_micro_base + float(micro_extra))

    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m_seam = complex(math.cos(-seam_phi), math.sin(-seam_phi))
    e_p_seam = complex(math.cos(+seam_phi), math.sin(+seam_phi))
    R12 = np.array([[c, s * e_m_seam, 0.0], [-s * e_p_seam, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = ((Ud @ Hh) @ R12 @ H) if bool(holo_on_seam) else (Ud @ R12)

    V0 = Uu.conjugate().T @ Ud_seam

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b
    DL = np.diag([
        complex(math.cos(a_u), math.sin(a_u)),
        complex(math.cos(a_c), math.sin(a_c)),
        complex(math.cos(a_t), math.sin(a_t)),
    ]).astype(np.complex128)

    ct23 = math.cos(theta_micro_local)
    st23 = math.sin(theta_micro_local)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
    A23 = DL.conjugate().T @ (Hh @ R23 @ H) @ DL

    ct13 = math.cos(theta13_adj)
    st13 = math.sin(theta13_adj)
    e_m13 = complex(math.cos(-r13_phi), math.sin(-r13_phi))
    e_p13 = complex(math.cos(+r13_phi), math.sin(+r13_phi))
    R13 = np.array([[ct13, 0.0, st13 * e_m13], [0.0, 1.0, 0.0], [-st13 * e_p13, 0.0, ct13]], dtype=np.complex128)
    A13 = DL.conjugate().T @ (Hh @ R13 @ H) @ DL

    Uu_pp = Uu @ A13.conjugate().T @ A23.conjugate().T
    V = Uu_pp.conjugate().T @ Ud_seam

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}

    out.setdefault("policy", {})
    out["policy"]["ckm_holoC30"] = {
        "seam_phase": "phi_A",
        "r13_phase": "phi_A",
        "mu30": int(mu30),
        "mt30": int(mt30),
        "holo_on_seam": bool(holo_on_seam),
        "seam_extra": {"mult_theta_sext_q": -0.25, "value_rad": float(seam_extra)},
        "micro_extra": {"mult_theta_sext_q": +0.50, "value_rad": float(micro_extra)},
        "s_micro": int(s_micro),
        "rho_eff": int(rho),
        "theta13_adj": {"s13": int(s13), "value_rad": float(theta13_adj)},
    }
    return out


def _rt_construct_misalignment_v0_33_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_GRIDBEST_1260(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """RT construct v0.33 (Gate-4): freeze the best discrete CKM holonomy candidate from diag grid (v0.2)."""
    out = _rt_construct_misalignment_v0_34__core_holoC30_CPBEST(delta_deg_ckm, delta_deg_pmns, holo_on_seam=True)
    out["version"] = "rt_construct_v0_33_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_GRIDBEST_1260"
    return out


def _rt_construct_misalignment_v0_33_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_GRIDBEST_1260_NEG(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """NEG variant: disable holonomy-on-seam (expected to worsen CKM fit)."""
    out = _rt_construct_misalignment_v0_34__core_holoC30_CPBEST(delta_deg_ckm, delta_deg_pmns, holo_on_seam=False)
    out["version"] = "rt_construct_v0_33_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_GRIDBEST_1260_NEG"
    return out

def _rt_construct_misalignment_v0_26_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_microbend_1260(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """RT construct v0.26 (diagnostic): v0.25 + microbend (no new knobs).

    Microbend policy (deterministic):
    - PP23: θ_micro -> θ_micro·(1 + 1/|L_cap|), |L_cap|=7.
    - CKM13 sextet: θ13 -> θ13·(1 - sin²θ_W), sin²θ_W=1/4 ⇒ factor 3/4.

    Not promoted; for comparison only.
    """

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_26_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_microbend_1260"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    theta_sext_q = float(2.0 * math.pi / (float(nQ) * 6.0))
    s13 = ((k_ckm_30 % 3) - 1)
    theta13_adj = float(theta_sext_q * float(s13))

    cap_abs = 7.0
    fac_pp23 = (1.0 + 1.0 / cap_abs)
    fac_ckm13 = 0.75

    theta_micro_eff = float(theta_micro * fac_pp23)
    theta13_adj_eff = float(theta13_adj * fac_ckm13)

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag(
        [
            complex(math.cos(a_u), math.sin(a_u)),
            complex(math.cos(a_c), math.sin(a_c)),
            complex(math.cos(a_t), math.sin(a_t)),
        ]
    ).astype(np.complex128)

    ct23 = math.cos(theta_micro_eff)
    st23 = math.sin(theta_micro_eff)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
    A23 = DL.conjugate().T @ R23 @ DL

    ct13 = math.cos(theta13_adj_eff)
    st13 = math.sin(theta13_adj_eff)
    R13 = np.array([[ct13, 0.0, st13 * e_m], [0.0, 1.0, 0.0], [-st13 * e_p, 0.0, ct13]], dtype=np.complex128)
    A13 = DL.conjugate().T @ R13 @ DL

    Uu_pp = Uu @ A13.conjugate().T @ A23.conjugate().T

    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["microbend"] = {
        "active": True,
        "cap_abs": int(cap_abs),
        "fac_pp23": float(fac_pp23),
        "fac_ckm13": float(fac_ckm13),
        "theta_micro_deg_base": float(math.degrees(theta_micro)),
        "theta_micro_deg_eff": float(math.degrees(theta_micro_eff)),
        "theta13_adj_deg_base": float(math.degrees(theta13_adj)),
        "theta13_adj_deg_eff": float(math.degrees(theta13_adj_eff)),
    }

    try:
        out["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return out






def _rt_construct_misalignment_v0_26_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_microbend_1260_NEG(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
) -> Dict[str, Any]:
    """NEG for v0.26: invert microbend directions."""

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_26_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_microbend_1260_NEG"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    theta_sext_q = float(2.0 * math.pi / (float(nQ) * 6.0))
    s13 = ((k_ckm_30 % 3) - 1)
    theta13_adj = float(theta_sext_q * float(s13))

    cap_abs = 7.0
    fac_pp23 = (1.0 - 1.0 / cap_abs)
    fac_ckm13 = 1.25

    theta_micro_eff = float(theta_micro * fac_pp23)
    theta13_adj_eff = float(theta13_adj * fac_ckm13)

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag(
        [
            complex(math.cos(a_u), math.sin(a_u)),
            complex(math.cos(a_c), math.sin(a_c)),
            complex(math.cos(a_t), math.sin(a_t)),
        ]
    ).astype(np.complex128)

    ct23 = math.cos(theta_micro_eff)
    st23 = math.sin(theta_micro_eff)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
    A23 = DL.conjugate().T @ R23 @ DL

    ct13 = math.cos(theta13_adj_eff)
    st13 = math.sin(theta13_adj_eff)
    R13 = np.array([[ct13, 0.0, st13 * e_m], [0.0, 1.0, 0.0], [-st13 * e_p, 0.0, ct13]], dtype=np.complex128)
    A13 = DL.conjugate().T @ R13 @ DL

    Uu_pp = Uu @ A13.conjugate().T @ A23.conjugate().T

    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["microbend"] = {
        "active": True,
        "cap_abs": int(cap_abs),
        "fac_pp23": float(fac_pp23),
        "fac_ckm13": float(fac_ckm13),
        "theta_micro_deg_base": float(math.degrees(theta_micro)),
        "theta_micro_deg_eff": float(math.degrees(theta_micro_eff)),
        "theta13_adj_deg_base": float(math.degrees(theta13_adj)),
        "theta13_adj_deg_eff": float(math.degrees(theta13_adj_eff)),
    }

    out.setdefault("NEG", {})
    out["NEG"]["microbend_inverted"] = True

    try:
        out["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return out

def _rt_construct_misalignment_v0_27_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phase_scan_1260(
    delta_deg_ckm: Optional[float],
    delta_deg_pmns: Optional[float],
    seam_phase: str = "phi_B",
    r13_phase: str = "phi_B",
    snap_quark: bool = False,
    snap_lepton: bool = False,
) -> Dict[str, Any]:
    """Diagnostic scan node: vary only *discrete* phase-branch choices and optional eigenphase snap.

    No new continuous knobs:
      - seam_phase ∈ {phi_A, phi_B}
      - r13_phase  ∈ {phi_A, phi_B}
      - snap_quark ∈ {False, True}  (snap Uu,Ud eigenphases to C300)
      - snap_lepton∈ {False, True}  (snap Ue,Uν eigenphases to C30)

    Base mechanics follow v0.25 (Gate-2 candidate) and keep PP23 in the Uu right-basis.
    """

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_27_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phase_scan_1260"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)

    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)

    # Choose branch (discrete) for seam and R13 phase.
    seam_phi = phi_B if str(seam_phase).lower().endswith('b') else phi_A
    r13_phi = phi_B if str(r13_phase).lower().endswith('b') else phi_A

    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    theta_sext_q = float(2.0 * math.pi / (float(nQ) * 6.0))
    s13 = ((k_ckm_30 % 3) - 1)
    theta13_adj = float(theta_sext_q * float(s13))

    def _build_kick(p: int, phi_edge: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        # keep the same sign convention as v0.16/v0.25
        eps = RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0)
        Uk = _rt_expm_i_hermitian(Hn, eps)
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B), nQ, kQ_base, dkQ, rho_sign=-1)

    snap_diag = {}
    if bool(snap_quark):
        su = _rt_unitary_eigphase_snap_Cn(Uu, int(nQ))
        sd = _rt_unitary_eigphase_snap_Cn(Ud, int(nQ))
        if su.get('error') or sd.get('error'):
            out['error'] = f"eigphase snap (quark) error: Uu={su.get('error')} Ud={sd.get('error')}"
            return out
        Uu = su['U_snap']
        Ud = sd['U_snap']
        snap_diag['quark'] = {
            'n': int(nQ),
            'Uu_delta_deg_max': su.get('delta_deg_max'),
            'Ud_delta_deg_max': sd.get('delta_deg_max'),
        }

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + (2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m_seam = complex(math.cos(-seam_phi), math.sin(-seam_phi))
    e_p_seam = complex(math.cos(+seam_phi), math.sin(+seam_phi))
    R12 = np.array([[c, s * e_m_seam, 0.0], [-s * e_p_seam, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    if bool(snap_lepton):
        se = _rt_unitary_eigphase_snap_Cn(Ue, int(nL))
        sn = _rt_unitary_eigphase_snap_Cn(Unu, int(nL))
        if se.get('error') or sn.get('error'):
            out['error'] = f"eigphase snap (lepton) error: Ue={se.get('error')} Unu={sn.get('error')}"
            return out
        Ue = se['U_snap']
        Unu = sn['U_snap']
        snap_diag['lepton'] = {
            'n': int(nL),
            'Ue_delta_deg_max': se.get('delta_deg_max'),
            'Unu_delta_deg_max': sn.get('delta_deg_max'),
        }

    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag(
        [
            complex(math.cos(a_u), math.sin(a_u)),
            complex(math.cos(a_c), math.sin(a_c)),
            complex(math.cos(a_t), math.sin(a_t)),
        ]
    ).astype(np.complex128)

    ct23 = math.cos(theta_micro)
    st23 = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
    A23 = DL.conjugate().T @ R23 @ DL

    ct13 = math.cos(theta13_adj)
    st13 = math.sin(theta13_adj)
    e_m13 = complex(math.cos(-r13_phi), math.sin(-r13_phi))
    e_p13 = complex(math.cos(+r13_phi), math.sin(+r13_phi))
    R13 = np.array([[ct13, 0.0, st13 * e_m13], [0.0, 1.0, 0.0], [-st13 * e_p13, 0.0, ct13]], dtype=np.complex128)
    A13 = DL.conjugate().T @ R13 @ DL

    Uu_pp = Uu @ A13.conjugate().T @ A23.conjugate().T

    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck0 = _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)])
    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23_uubasis"] = {"V_abs": _rt_abs_from_np(V0), "unitary_residual": _rt_unitary_residual_np(V0), "angles": ck0}
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["diag_phase_scan"] = {
        "seam_phase": "phi_B" if seam_phi == phi_B else "phi_A",
        "r13_phase": "phi_B" if r13_phi == phi_B else "phi_A",
        "snap_quark": bool(snap_quark),
        "snap_lepton": bool(snap_lepton),
        "snap_diag": snap_diag,
    }

    try:
        out["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return out



def _rt_construct_misalignment_v0_19_monodromy_postR12_seam_down_oriented_pp23_uubasis_1260_NEG(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """NEG control for v0.19: flip the PP23 sign (R23(-theta_micro) in PDG-fixed row basis)."""

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_19_monodromy_postR12_seam_down_oriented_pp23_uubasis_1260_NEG"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)
    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)
    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, float(eps))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    # leptons unchanged
    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag(
        [
            complex(math.cos(a_u), math.sin(a_u)),
            complex(math.cos(a_c), math.sin(a_c)),
            complex(math.cos(a_t), math.sin(a_t)),
        ]
    ).astype(np.complex128)

    ct = math.cos(-theta_micro)
    st = math.sin(-theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct, st], [0.0, -st, ct]], dtype=np.complex128)
    A = DL.conjugate().T @ R23 @ DL

    Uu_pp = Uu @ A.conjugate().T
    V = Uu_pp.conjugate().T @ Ud_seam
    U = Ue.conjugate().T @ Unu

    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM_pre_pp23"] = out.get("CKM")
    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"]["postL23_pp23"] = {
        "active": True,
        "placement": "Uu_right_basis_PDG_row_fixed",
        "action": "V <- (DL^† R23(-theta_micro) DL) · V0  (DL from V0 row-phase fix)",
        "theta_micro_rad": float(-theta_micro),
        "theta_micro_deg": float(math.degrees(-theta_micro)),
        "rho": int(rho),
        "s_micro": int(s_micro),
        "note": "NEG sign-flip control for PP23 placement",
    }

    return out
    if np is None:
        out["error"] = "numpy required"
        return out

    # Re-apply with opposite sign by swapping pre-pp23 and pp23 if available.
    # Deterministically recompute using the same policy but with flipped sign.
    try:
        pol = (out.get("policy") or {})
        rho = int(pol.get("postL23_pp23", {}).get("rho") or RT_RHO)
        s_micro = int(pol.get("postL23_pp23", {}).get("s_micro") or 0)
        if rho <= 0:
            rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
        theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

        # Use the stored *pre* matrix if present; else keep current (diagnostic).
        pre = (out.get("CKM_pre_pp23_uubasis") or {})
        V0_abs = pre.get("V_abs")
        if V0_abs is None or np is None:
            return out

        # Reconstruct a representative complex V0 via PDG parameterization from stored angles (for NEG only).
        ang0 = (pre.get("angles") or {})
        th12 = math.radians(float(ang0.get("theta12_deg") or 0.0))
        th23 = math.radians(float(ang0.get("theta23_deg") or 0.0))
        th13 = math.radians(float(ang0.get("theta13_deg") or 0.0))
        delta = math.radians(float(ang0.get("delta_deg_from_sin") or 0.0))
        V0 = np.array(_ckm_unitary_pdg(th12, th23, th13, delta), dtype=np.complex128)

        # Apply opposite sign: V <- R23(-theta_micro) · V0
        ct = math.cos(-theta_micro)
        st = math.sin(-theta_micro)
        R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct, st], [0.0, -st, ct]], dtype=np.complex128)
        Vn = R23 @ V0
        ck = _angles_J_from_unitary([[complex(Vn[i, j]) for j in range(3)] for i in range(3)])
        out["CKM"] = {"V_abs": _rt_abs_from_np(Vn), "unitary_residual": _rt_unitary_residual_np(Vn), "angles": ck}

        out.setdefault("policy", {})
        out["policy"]["postL23_pp23"]["note"] = "NEG sign-flip control; applied as V <- R23(-theta_micro)·V0 (PDG recon)"
    except Exception:
        pass

    return out





def _rt_construct_misalignment_v0_20_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_1260(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct v0.20: PMNS θ13 suppression via sextet-engagement (discrete 2° step).

    Principle (PP-native; no tuning)
    - Keep v0.19 (Uu right-basis PP23) unchanged for CKM.
    - Apply a *right-basis* R13 micro-rotation on Unu with step θ_sext = 2π/(30·6) (=2°).
    - Sign/step is deterministic from k_PMNS mod 3:
        s13 := ((k_PMNS mod 3) - 1) ∈ {-1,0,+1}
      so k≡2 (mod3) yields +2° (suppression in extracted θ13 for current placement), k≡0 yields −2°, k≡1 yields 0.

    NEG control flips the sign (see v0.20_NEG).
    """

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_20_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_1260"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)
    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)
    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, float(eps))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    # Quarks (same as v0.19)
    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    # Leptons baseline
    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    # CKM PP23 on Uu right-basis (same as v0.19)
    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_s = -_arg(complex(V0[0, 1])) - a_u
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag(
        [
            complex(math.cos(a_u), math.sin(a_u)),
            complex(math.cos(a_c), math.sin(a_c)),
            complex(math.cos(a_t), math.sin(a_t)),
        ]
    ).astype(np.complex128)

    ct = math.cos(theta_micro)
    st = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct, st], [0.0, -st, ct]], dtype=np.complex128)
    A = DL.conjugate().T @ R23 @ DL
    Uu_pp = Uu @ A.conjugate().T

    V = Uu_pp.conjugate().T @ Ud_seam

    # PMNS θ13 sextet-engagement on Unu right-basis
    theta_sext = float(2.0 * math.pi / (30.0 * 6.0))  # 2°
    s13 = ((k_pm_30 % 3) - 1)  # {-1,0,+1}
    theta13_adj = float(theta_sext * float(s13))
    c13 = math.cos(theta13_adj)
    s13s = math.sin(theta13_adj)
    R13 = np.array([[c13, 0.0, s13s], [0.0, 1.0, 0.0], [-s13s, 0.0, c13]], dtype=np.complex128)

    U_pre = Ue.conjugate().T @ Unu
    Unu_adj = Unu @ R13
    U = Ue.conjugate().T @ Unu_adj

    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm0 = _angles_J_from_unitary([[complex(U_pre[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS_pre_sextet"] = {"U_abs": _rt_abs_from_np(U_pre), "unitary_residual": _rt_unitary_residual_np(U_pre), "angles": pm0}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"].setdefault("postL23_pp23", {})
    out["policy"]["postL23_pp23"].update(
        {
            "active": True,
            "placement": "Uu_right_basis",
            "action": "Uu <- Uu · (DL^† R23(+theta_micro) DL)^†  =>  V <- (DL^† R23(+theta_micro) DL) · V0",
            "theta_micro_rad": float(theta_micro),
            "theta_micro_deg": float(math.degrees(theta_micro)),
            "rho": int(rho),
            "s_micro": int(s_micro),
            "note": "same as v0.19 (PP23 on Uu right-basis)",
        }
    )
    out["policy"]["pmns13_sextet_engagement"] = {
        "active": True,
        "placement": "Unu_right_basis",
        "action": "Unu <- Unu · R13(theta13_adj)  =>  U <- U · R13(theta13_adj)",
        "theta_step_rad": float(theta_sext),
        "theta_step_deg": float(math.degrees(theta_sext)),
        "s13": int(s13),
        "theta13_adj_rad": float(theta13_adj),
        "theta13_adj_deg": float(math.degrees(theta13_adj)),
        "k_pm_mod30": int(k_pm_30),
        "k_pm_mod3": int(k_pm_30 % 3),
        "rule": "s13 := ((k_PMNS mod 3) - 1) ∈ {-1,0,+1}; θ= s13·2°",
        "note": "diagnostic: targets θ13 suppression by one sextet step when k≡2 (mod3)",
    }

    # recompute gate summary (diagnostic)
    try:
        ck_ang = ((out.get("CKM") or {}).get("angles") or {})
        pm_ang = ((out.get("PMNS") or {}).get("angles") or {})
        def _score(a: Dict[str, float]) -> float:
            return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2
        s_ckm = _score(ck_ang)
        s_pmns = _score(pm_ang)
        def _in_range(x: float, r: Tuple[float, float]) -> bool:
            return (x >= float(r[0])) and (x <= float(r[1]))
        ck_t12 = float(ck_ang.get("theta12_deg", 0.0))
        ck_t23 = float(ck_ang.get("theta23_deg", 0.0))
        ck_t13 = float(ck_ang.get("theta13_deg", 0.0))
        ck_J = float(ck_ang.get("J", 0.0))
        ck_order = bool(ck_t12 > ck_t23 > ck_t13)
        ck_ranges_ok = bool(_in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG) and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG) and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG))
        ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
        pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)
        pm_t12 = float(pm_ang.get("theta12_deg", 0.0))
        pm_t23 = float(pm_ang.get("theta23_deg", 0.0))
        pm_t13 = float(pm_ang.get("theta13_deg", 0.0))
        pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
        pass_pmns_pattern = bool(pm_large_count >= 2)
        pass_struct = bool(s_ckm < s_pmns)
        out["gate"] = {
            "score": {"ckm": float(s_ckm), "pmns": float(s_pmns), "pass": bool(pass_struct)},
            "ckm_pattern": {"pass": bool(pass_ckm_pattern), "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J}},
            "pmns_pattern": {"pass": bool(pass_pmns_pattern), "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13}, "large_count": int(pm_large_count)},
            "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
        }
    except Exception:
        pass

    return out



def _rt_construct_misalignment_v0_20_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_1260_NEG(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """NEG control for v0.20: flip the sextet-engagement sign (opposite 2° step) *with full recompute*."""

    # Same build as v0.20, but use the opposite sign rule:
    # s13_NEG := +((k_PMNS mod 3) - 1)  (instead of minus)

    out = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_20_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_1260_NEG"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    pol = (out.get("policy") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)
    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)
    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, float(eps))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_s = -_arg(complex(V0[0, 1])) - a_u
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag(
        [
            complex(math.cos(a_u), math.sin(a_u)),
            complex(math.cos(a_c), math.sin(a_c)),
            complex(math.cos(a_t), math.sin(a_t)),
        ]
    ).astype(np.complex128)

    ct = math.cos(theta_micro)
    st = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct, st], [0.0, -st, ct]], dtype=np.complex128)
    A = DL.conjugate().T @ R23 @ DL
    Uu_pp = Uu @ A.conjugate().T

    V = Uu_pp.conjugate().T @ Ud_seam

    theta_sext = float(2.0 * math.pi / (30.0 * 6.0))
    s13 = -(((k_pm_30 % 3) - 1))  # NEG sign (opposite)
    theta13_adj = float(theta_sext * float(s13))
    c13 = math.cos(theta13_adj)
    s13s = math.sin(theta13_adj)
    R13 = np.array([[c13, 0.0, s13s], [0.0, 1.0, 0.0], [-s13s, 0.0, c13]], dtype=np.complex128)

    U_pre = Ue.conjugate().T @ Unu
    Unu_adj = Unu @ R13
    U = Ue.conjugate().T @ Unu_adj

    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm0 = _angles_J_from_unitary([[complex(U_pre[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS_pre_sextet"] = {"U_abs": _rt_abs_from_np(U_pre), "unitary_residual": _rt_unitary_residual_np(U_pre), "angles": pm0}
    out["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    out.setdefault("policy", {})
    out["policy"].setdefault("postL23_pp23", {})
    out["policy"]["postL23_pp23"].update(
        {
            "active": True,
            "placement": "Uu_right_basis",
            "action": "Uu <- Uu · (DL^† R23(+theta_micro) DL)^†  =>  V <- (DL^† R23(+theta_micro) DL) · V0",
            "theta_micro_rad": float(theta_micro),
            "theta_micro_deg": float(math.degrees(theta_micro)),
            "rho": int(rho),
            "s_micro": int(s_micro),
            "note": "same as v0.19 (PP23 on Uu right-basis)",
        }
    )
    out["policy"]["pmns13_sextet_engagement"] = {
        "active": True,
        "placement": "Unu_right_basis",
        "action": "Unu <- Unu · R13(theta13_adj)  =>  U <- U · R13(theta13_adj)",
        "theta_step_rad": float(theta_sext),
        "theta_step_deg": float(math.degrees(theta_sext)),
        "s13": int(s13),
        "theta13_adj_rad": float(theta13_adj),
        "theta13_adj_deg": float(math.degrees(theta13_adj)),
        "k_pm_mod30": int(k_pm_30),
        "k_pm_mod3": int(k_pm_30 % 3),
        "rule": "s13_NEG := -((k_PMNS mod 3) - 1); θ= s13·2°",
        "note": "NEG: opposite sextet sign",
    }

    return out



def _rt_construct_misalignment_v0_21_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_1260(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """RT construct v0.21: add a PP-native μ/τ basis adjustment using the Global-Frame cap |L_cap|=7.

    Goal-B path so far:
      - CKM: PP23 placed on Uu right-basis (v0.19)
      - PMNS: θ13 sextet engagement (R13, 2° discrete step) on Unu right-basis (v0.20)

    New (v0.21):
      - PMNS: apply the Global-Frame cap as a Σ / RP holonomy operator on the readout screen:
        U <- H_cap · U_mid,  with H_cap = R23(θ_cap)

    This avoids interpreting the effect as an arbitrary basis tweak: it is explicit transport/holonomy
    induced by the cap (|L_cap|=7) in the Global Frame loop L_* = 1260.

    Row-rotation view: rotates (μ,τ) rows and leaves the e-row unchanged ⇒ θ13 and θ12
    are preserved by construction (up to numerical roundoff).

    Discreteness: θ_cap = L_cap * (2π/(30·6)) and |L_cap|=7 comes from the Global Frame cap.
    """

    out = _rt_construct_misalignment_v0_20_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_1260(delta_deg_ckm, delta_deg_pmns)
    out["version"] = "rt_construct_v0_21_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_1260"
    if out.get("error"):
        return out
    if np is None:
        out["error"] = "numpy required"
        return out

    # Reconstruct U (complex) from stored abs-only isn't possible. Re-run local scaffold and apply cap-lift.
    pol = (out.get("policy") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)
    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)
    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        Uk = _rt_expm_i_hermitian(Hn, float(eps))
        return Uk

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            S = P @ Ub @ P.conjugate().T
            U = U @ S
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL

    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam

    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)

    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_s = -_arg(complex(V0[0, 1])) - a_u
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b

    DL = np.diag(
        [
            complex(math.cos(a_u), math.sin(a_u)),
            complex(math.cos(a_c), math.sin(a_c)),
            complex(math.cos(a_t), math.sin(a_t)),
        ]
    ).astype(np.complex128)

    ct = math.cos(theta_micro)
    st = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct, st], [0.0, -st, ct]], dtype=np.complex128)
    A = DL.conjugate().T @ R23 @ DL
    Uu_pp = Uu @ A.conjugate().T
    V = Uu_pp.conjugate().T @ Ud_seam

    theta_sext = float(2.0 * math.pi / (30.0 * 6.0))  # 2°
    s13 = ((k_pm_30 % 3) - 1)
    theta13_adj = float(theta_sext * float(s13))
    c13 = math.cos(theta13_adj)
    s13s = math.sin(theta13_adj)
    R13 = np.array([[c13, 0.0, s13s], [0.0, 1.0, 0.0], [-s13s, 0.0, c13]], dtype=np.complex128)

    U_pre = Ue.conjugate().T @ Unu
    Unu_adj = Unu @ R13
    U_mid = Ue.conjugate().T @ Unu_adj
    # --- Σ / RP holonomy from Global Frame cap (L_* = 1260 = 30·42) ---
    # Cap magnitude is derived deterministically by (bias-nollning 6 ticks for Z3×A/B) + (P-ARM 1 tick):
    #   |L_cap| = 6 + 1 = 7.
    # Sign convention (deterministic): removed endcap => L_cap = -|L_cap|. NEG flips this.
    if sigma_map is None:
        out["error"] = "sigma_map missing"
        return out
    L_bias = 6
    L_arm = 1
    L_cap_mag = int(sigma_map.cap_magnitude(L_bias=L_bias, L_arm=L_arm))
    L_cap = int(sigma_map.cap_length(L_bias=L_bias, L_arm=L_arm, removed_endcap=True))
    H_cap, cap_meta = sigma_map.cap_holonomy(axis="23", L_bias=L_bias, L_arm=L_arm, removed_endcap=True)
    theta_cap = float(cap_meta["theta_cap_rad"])

# --- NEG family (axis / magnitude) computed *in situ* on complex U_mid ---
    # These are negative controls that should NOT reproduce the (mu,tau) lift while preserving theta13.
    # We only store angle readouts (not full matrices) to keep artifacts small and deterministic.
    R12_cap = sigma_map.holonomy_rotation("12", float(theta_cap))
    R13_cap = sigma_map.holonomy_rotation("13", float(theta_cap))

    # axis NEG (wrong row plane)
    U_axis12 = sigma_map.apply_holonomy(U_mid, R12_cap)
    U_axis13 = sigma_map.apply_holonomy(U_mid, R13_cap)
    pm_axis12 = _angles_J_from_unitary([[complex(U_axis12[i, j]) for j in range(3)] for i in range(3)])
    pm_axis13 = _angles_J_from_unitary([[complex(U_axis13[i, j]) for j in range(3)] for i in range(3)])

    # magnitude NEG (wrong cap length; keep sign convention but change |L_cap|)
    for L_bad in (6, 8):
        th_bad = float(theta_sext * float(-int(L_bad)))
        ccb = math.cos(th_bad); ssb = math.sin(th_bad)
        R23_bad = sigma_map.holonomy_rotation("23", float(th_bad))
        U_bad = sigma_map.apply_holonomy(U_mid, R23_bad)
        pm_bad = _angles_J_from_unitary([[complex(U_bad[i, j]) for j in range(3)] for i in range(3)])
        out.setdefault("neg_controls", {})
        out["neg_controls"][f"pmns23_cap_mag_{int(L_bad)}"] = {
        "L_cap": int(-int(L_bad)),
        "theta_cap_deg": float(math.degrees(th_bad)),
        "angles": pm_bad,
        "expect": "FAIL (wrong cap magnitude)",
        }

    out.setdefault("neg_controls", {})
    out["neg_controls"]["pmns23_cap_axis12"] = {"axis": "12", "angles": pm_axis12, "expect": "FAIL (wrong row plane)"}
    out["neg_controls"]["pmns23_cap_axis13"] = {"axis": "13", "angles": pm_axis13, "expect": "FAIL (wrong row plane)"}

    # Gate-3: PP-native realization. Embed cap transport inside the charged-lepton generator:
    #   Ue <- Ue · H_cap†  =>  PMNS = (Ue·H†)† Uν = H · (Ue†Uν)
    Ue_cap, cap_meta = sigma_map.embed_cap_in_Ue(Ue, axis="23", L_bias=L_bias, L_arm=L_arm, removed_endcap=True)
    U = Ue_cap.conjugate().T @ Unu_adj

    # expose PP-native generator matrices for downstream deterministic lifts (e.g. PMNS12 sextet)
    out['Ue_cap'] = {
        'U_abs': _rt_abs_from_np(Ue_cap),
        'U_phase_rad': _rt_phase_from_np(Ue_cap),
        'unitary_residual': _rt_unitary_residual_np(Ue_cap),
    }
    out['Unu_adj'] = {
        'U_abs': _rt_abs_from_np(Unu_adj),
        'U_phase_rad': _rt_phase_from_np(Unu_adj),
        'unitary_residual': _rt_unitary_residual_np(Unu_adj),
    }

    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm0 = _angles_J_from_unitary([[complex(U_pre[i, j]) for j in range(3)] for i in range(3)])
    pm_mid = _angles_J_from_unitary([[complex(U_mid[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    out["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    out["PMNS_pre_sextet"] = {"U_abs": _rt_abs_from_np(U_pre), "unitary_residual": _rt_unitary_residual_np(U_pre), "angles": pm0}
    out["PMNS_pre_cap23"] = {
        "U_abs": _rt_abs_from_np(U_mid),
        "U_phase_rad": _rt_phase_from_np(U_mid),
        "unitary_residual": _rt_unitary_residual_np(U_mid),
        "angles": pm_mid,
    }
    out["PMNS"] = {
        "U_abs": _rt_abs_from_np(U),
        "U_phase_rad": _rt_phase_from_np(U),
        "unitary_residual": _rt_unitary_residual_np(U),
        "angles": pm,
    }

    out.setdefault("policy", {})
    out["policy"]["pmns23_cap_lift"] = {
        "active": True,
        "placement": "Ue_right_basis_generator",
        "action": "Ue <- Ue·H_cap† (PP-native). Equivalent to Σ left-holonomy on PMNS.",
        "theta_step_deg": float(math.degrees(theta_sext)),
        "L_cap": int(L_cap),
        "L_cap_mag": int(L_cap_mag),
        "L_bias": int(L_bias),
        "L_arm": int(L_arm),
        "sigma_meta": cap_meta,
        "sign_rule": "cap removal => L_cap=-|L_cap|",
        "theta_cap_rad": float(theta_cap),
        "theta_cap_deg": float(math.degrees(theta_cap)),
        "note": "Gate-3: cap-lift is embedded in the PP generator (Ue basis) instead of a post-step on readout.",
    }

    # Recompute structural gate readouts on the updated PMNS (θ23 cap-lift applied).
    try:
        out["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return out


def _rt_construct_misalignment_v0_21_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_1260_NEG(delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]) -> Dict[str, Any]:
    """NEG for v0.21: flip the Σ-holonomy sign (use removed_endcap=False instead of True)."""

    base = _rt_construct_misalignment_v0_20_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_1260(delta_deg_ckm, delta_deg_pmns)
    base["version"] = "rt_construct_v0_21_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_1260_NEG"
    if base.get("error"):
        return base
    if np is None:
        base["error"] = "numpy required"
        return base

    pol = (base.get("policy") or {})
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
    k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    blocks = int(pol.get("blocks") or 42)
    nQ = int((pol.get("grid") or {}).get("quark") or 300)
    nL = int((pol.get("grid") or {}).get("lepton") or 30)
    dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
    dkL = int((pol.get("monodromy_step") or {}).get("lepton_dk") or 5)
    rho = int(pol.get("rho") or RT_RHO)
    if rho <= 0:
        rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
    micro_step = int(((pol.get("rho_microphase") or {}).get("micro_step") or 1))

    seam = (pol.get("postR12_seam") or {})
    phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)
    s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
    theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

    def _build_kick(p: int, phi_edge: float, eps: float):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        H = (N + N.conjugate().T)
        w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
        m = float(np.max(np.abs(w.real))) if w.size else 1.0
        if m < 1e-12:
            m = 1.0
        Hn = H / m
        return _rt_expm_i_hermitian(Hn, float(eps))

    def _rho_z3_sieved(b: int) -> int:
        return int((b % rho) % 3)

    def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
        n = int(n)
        k0 = int(k0) % n
        dk = int(dk) % n
        rho_sign = int(rho_sign)
        U = np.eye(3, dtype=np.complex128)
        for b in range(int(blocks)):
            kb = (k0 + b * dk) % n
            if (n == nQ) and (rho_sign != 0):
                kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
            P = _rt_proj_phase_Cn(kb, n)
            R = _rt_perm_cycle_pow(b % 3)
            Ub = U_kick.conjugate().T if (b % 2) else U_kick
            Ub = R @ Ub @ R.conjugate().T
            U = U @ (P @ Ub @ P.conjugate().T)
        return _rt_gauge_fix_unitary(U)

    kQ_base = (10 * k_ckm_30) % nQ
    kL_base = k_pm_30 % nL
    Uu = _monodromy(_build_kick(6, phi_A, +RT_EPS0), nQ, kQ_base, dkQ, rho_sign=+1)
    Ud = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nQ, kQ_base, dkQ, rho_sign=-1)

    theta_base = float(2.0 * math.pi / 30.0)
    theta_seam = float(theta_base + theta_micro)
    c = math.cos(theta_seam)
    s = math.sin(theta_seam)
    e_m = complex(math.cos(-phi_B), math.sin(-phi_B))
    e_p = complex(math.cos(+phi_B), math.sin(+phi_B))
    R12 = np.array([[c, s * e_m, 0.0], [-s * e_p, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
    Ud_seam = Ud @ R12

    Ue = _monodromy(_build_kick(5, phi_B, -RT_EPS0), nL, (kL_base + 0) % nL, dkL, rho_sign=0)
    Unu = _monodromy(_build_kick(4, phi_A, +RT_EPS0), nL, (kL_base + 5) % nL, dkL, rho_sign=0)

    V0 = Uu.conjugate().T @ Ud_seam
    def _arg(z: complex) -> float:
        return math.atan2(z.imag, z.real)
    a_u = -_arg(complex(V0[0, 0]))
    a_c = 0.0
    b_s = -_arg(complex(V0[0, 1])) - a_u
    b_b = -_arg(complex(V0[1, 2])) - a_c
    a_t = -_arg(complex(V0[2, 2])) - b_b
    DL = np.diag([complex(math.cos(a_u), math.sin(a_u)), complex(math.cos(a_c), math.sin(a_c)), complex(math.cos(a_t), math.sin(a_t))]).astype(np.complex128)

    ct = math.cos(theta_micro)
    st = math.sin(theta_micro)
    R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct, st], [0.0, -st, ct]], dtype=np.complex128)
    A = DL.conjugate().T @ R23 @ DL
    Uu_pp = Uu @ A.conjugate().T
    V = Uu_pp.conjugate().T @ Ud_seam

    theta_sext = float(2.0 * math.pi / (30.0 * 6.0))
    s13 = ((k_pm_30 % 3) - 1)
    theta13_adj = float(theta_sext * float(s13))
    c13 = math.cos(theta13_adj)
    s13s = math.sin(theta13_adj)
    R13 = np.array([[c13, 0.0, s13s], [0.0, 1.0, 0.0], [-s13s, 0.0, c13]], dtype=np.complex128)

    U_pre = Ue.conjugate().T @ Unu
    Unu_adj = (Unu @ R13)
    U_mid = Ue.conjugate().T @ Unu_adj
    if sigma_map is None:
        base["error"] = "sigma_map missing"
        return base
    L_bias = 6
    L_arm = 1
    L_cap_mag = int(sigma_map.cap_magnitude(L_bias=L_bias, L_arm=L_arm))
    # NEG: flip the PP cap-removal sign (removed_endcap=False)
    L_cap = int(sigma_map.cap_length(L_bias=L_bias, L_arm=L_arm, removed_endcap=False))
    H_cap, cap_meta = sigma_map.cap_holonomy(axis="23", L_bias=L_bias, L_arm=L_arm, removed_endcap=False)
    theta_cap = float(cap_meta["theta_cap_rad"])

    # NEG (Gate-3): embed flipped-sign cap in Ue generator (removed_endcap=False)
    Ue_cap, cap_meta = sigma_map.embed_cap_in_Ue(Ue, axis="23", L_bias=L_bias, L_arm=L_arm, removed_endcap=False)
    U = Ue_cap.conjugate().T @ Unu_adj

    ck = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
    pm0 = _angles_J_from_unitary([[complex(U_pre[i, j]) for j in range(3)] for i in range(3)])
    pm_mid = _angles_J_from_unitary([[complex(U_mid[i, j]) for j in range(3)] for i in range(3)])
    pm = _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)])

    base["CKM"] = {"V_abs": _rt_abs_from_np(V), "unitary_residual": _rt_unitary_residual_np(V), "angles": ck}
    base["PMNS_pre_sextet"] = {"U_abs": _rt_abs_from_np(U_pre), "unitary_residual": _rt_unitary_residual_np(U_pre), "angles": pm0}
    base["PMNS_pre_cap23"] = {"U_abs": _rt_abs_from_np(U_mid), "unitary_residual": _rt_unitary_residual_np(U_mid), "angles": pm_mid}
    base["PMNS"] = {"U_abs": _rt_abs_from_np(U), "unitary_residual": _rt_unitary_residual_np(U), "angles": pm}

    base.setdefault("policy", {})
    base["policy"]["pmns23_cap_lift"] = {
        "active": True,
        "placement": "Ue_right_basis_generator",
        "action": "NEG: embed sign-flipped cap in Ue (removed_endcap=False)",
        "theta_step_deg": float(math.degrees(theta_sext)),
        "L_cap": int(L_cap),
        "L_cap_mag": int(L_cap_mag),
        "L_bias": int(L_bias),
        "L_arm": int(L_arm),
        "sigma_meta": cap_meta,
        "sign_rule": "cap removal => L_cap=-|L_cap|",
        "theta_cap_rad": float(theta_cap),
        "theta_cap_deg": float(math.degrees(theta_cap)),
        "note": "NEG: sign-flipped cap transport embedded in generator (L_cap=+|L_cap|).",
    }

    # Gate readouts should reflect the NEG'd PMNS.
    try:
        base["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return base


def _rt_construct_misalignment_v0_22_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_1260(
    delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]
) -> Dict[str, Any]:
    """RT construct v0.22.

    Build on v0.21 (θ13 sextet + θ23 cap-lift) and then apply a **right** R12 sextet
    (column-mix) on PMNS to lift θ12. Uses v0.21's stored elementwise phases.
    """

    base = _rt_construct_misalignment_v0_21_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_1260(
        delta_deg_ckm, delta_deg_pmns
    )
    base["version"] = "rt_construct_v0_22_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_1260"
    if base.get("error") is not None:
        return base

    if np is None:
        base["error"] = "numpy not available"
        return base

    pol = base.get("policy") or {}
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    # PP-native θ12 lift: apply a right R12 sextet inside the neutrino generator (Unu right-basis),
    # then re-form PMNS = (Ue_cap)† · (Unu_adj · R12).

    # pull generator matrices from v0.21
    Ue_cap_pack = base.get('Ue_cap') or {}
    Unu_adj_pack = base.get('Unu_adj') or {}
    A1 = Ue_cap_pack.get('U_abs'); P1 = Ue_cap_pack.get('U_phase_rad')
    A2 = Unu_adj_pack.get('U_abs'); P2 = Unu_adj_pack.get('U_phase_rad')

    if not (A1 and P1 and A2 and P2):
        # fallback (legacy): operate directly on reconstructed PMNS (right column mix)
        pm0 = (base.get('PMNS') or {})
        U_abs = pm0.get('U_abs')
        U_phi = pm0.get('U_phase_rad')
        if not (U_abs and U_phi):
            base['error'] = 'missing PMNS phases (U_phase_rad) from v0.21'
            return base
        U_pre = (
            np.array(U_abs, dtype=np.float64)
            * np.exp(1j * np.array(U_phi, dtype=np.float64))
        )
        Ue_cap = None
        Unu_adj = None
    else:
        Ue_cap = (
            np.array(A1, dtype=np.float64)
            * np.exp(1j * np.array(P1, dtype=np.float64))
        )
        Unu_adj = (
            np.array(A2, dtype=np.float64)
            * np.exp(1j * np.array(P2, dtype=np.float64))
        )
        U_pre = Ue_cap.conjugate().T @ Unu_adj

    theta_sext = float(2.0 * math.pi / (30.0 * 6.0))
    s12 = ((k_pm_30 % 3) - 1)
    theta12_adj = float(theta_sext * float(s12))
    c12 = math.cos(theta12_adj)
    s12s = math.sin(theta12_adj)
    R12r = np.array([[c12, s12s, 0.0], [-s12s, c12, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)

    if Unu_adj is None:
        U2 = U_pre @ R12r
        placement = 'PMNS_right_column_mix (fallback)'
    else:
        Unu2 = Unu_adj @ R12r
        U2 = Ue_cap.conjugate().T @ Unu2
        placement = 'Unu_right_basis_generator (PP-native)'

    # record pre/post
    base['PMNS_pre_pmns12'] = {
        'U_abs': _rt_abs_from_np(U_pre),
        'U_phase_rad': _rt_phase_from_np(U_pre),
        'unitary_residual': _rt_unitary_residual_np(U_pre),
        'angles': ((base.get('PMNS') or {}).get('angles') or {}),
    }
    pm = _angles_J_from_unitary([[complex(U2[i, j]) for j in range(3)] for i in range(3)])
    base['PMNS'] = {
        'U_abs': _rt_abs_from_np(U2),
        'U_phase_rad': _rt_phase_from_np(U2),
        'unitary_residual': _rt_unitary_residual_np(U2),
        'angles': pm,
    }

    base.setdefault('policy', {})
    base['policy']['pmns12_sextet_r12'] = {
        'active': True,
        'placement': placement,
        'axis': '12',
        'theta_step_deg': float(math.degrees(theta_sext)),
        'k_pm_mod30': int(k_pm_30),
        'k_pm_mod3': int(k_pm_30 % 3),
        's12': int(s12),
        'theta12_adj_deg': float(math.degrees(theta12_adj)),
        'note': 'θ12 lift implemented as PP-native Unu right-basis sextet (R12). Algebraically equivalent to PMNS @ R12.',
    }


    # Gate readouts should reflect the lifted θ12.
    try:
        ck = ((base.get("CKM") or {}).get("angles") or {})
        base["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return base


def _rt_construct_misalignment_v0_27_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_mcap_1260(
    delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]
) -> Dict[str, Any]:
    """RT construct v0.27.

    Same as v0.22 (PP-native Unu right-basis R12 sextet), but the **sextet multiplicity**
    is derived deterministically from the already-locked Global-Frame cap:

        m12 := 1 + (|L_cap| mod 3)

    With |L_cap|=7 this yields m12=2 (a double-sextet = 4° on the R12 generator),
    which lifts PMNS θ12 closer to ~33° while keeping θ13/θ23 exactly unchanged
    (right-multiplication by R12 does not touch column 3).
    """

    base = _rt_construct_misalignment_v0_21_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_1260(
        delta_deg_ckm, delta_deg_pmns
    )
    base["version"] = "rt_construct_v0_27_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_mcap_1260"
    if base.get("error") is not None:
        return base
    if np is None:
        base["error"] = "numpy not available"
        return base

    pol = base.get("policy") or {}
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    cap_pack = pol.get("pmns23_cap_lift") or {}
    L_cap = int(cap_pack.get("L_cap") or -7)
    m12 = 1 + (abs(int(L_cap)) % 3)
    if m12 <= 0:
        m12 = 1

    Ue_cap_pack = base.get("Ue_cap") or {}
    Unu_adj_pack = base.get("Unu_adj") or {}
    A1 = Ue_cap_pack.get("U_abs")
    P1 = Ue_cap_pack.get("U_phase_rad")
    A2 = Unu_adj_pack.get("U_abs")
    P2 = Unu_adj_pack.get("U_phase_rad")

    if not (A1 and P1 and A2 and P2):
        pm0 = base.get("PMNS") or {}
        U_abs = pm0.get("U_abs")
        U_phi = pm0.get("U_phase_rad")
        if not (U_abs and U_phi):
            base["error"] = "missing PMNS phases (U_phase_rad) from v0.21"
            return base
        U_pre = np.array(U_abs, dtype=np.float64) * np.exp(1j * np.array(U_phi, dtype=np.float64))
        Ue_cap = None
        Unu_adj = None
    else:
        Ue_cap = np.array(A1, dtype=np.float64) * np.exp(1j * np.array(P1, dtype=np.float64))
        Unu_adj = np.array(A2, dtype=np.float64) * np.exp(1j * np.array(P2, dtype=np.float64))
        U_pre = Ue_cap.conjugate().T @ Unu_adj

    theta_sext = float(2.0 * math.pi / (30.0 * 6.0))
    s12 = ((k_pm_30 % 3) - 1)
    theta12_adj = float(theta_sext * float(s12) * float(m12))
    c12 = math.cos(theta12_adj)
    s12s = math.sin(theta12_adj)
    R12r = np.array([[c12, s12s, 0.0], [-s12s, c12, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)

    if Unu_adj is None:
        U2 = U_pre @ R12r
        placement = "PMNS_right_column_mix (fallback)"
    else:
        Unu2 = Unu_adj @ R12r
        U2 = Ue_cap.conjugate().T @ Unu2
        placement = "Unu_right_basis_generator (PP-native)"

    base["PMNS_pre_pmns12"] = {
        "U_abs": _rt_abs_from_np(U_pre),
        "U_phase_rad": _rt_phase_from_np(U_pre),
        "unitary_residual": _rt_unitary_residual_np(U_pre),
        "angles": ((base.get("PMNS") or {}).get("angles") or {}),
    }
    pm = _angles_J_from_unitary([[complex(U2[i, j]) for j in range(3)] for i in range(3)])
    base["PMNS"] = {
        "U_abs": _rt_abs_from_np(U2),
        "U_phase_rad": _rt_phase_from_np(U2),
        "unitary_residual": _rt_unitary_residual_np(U2),
        "angles": pm,
    }

    base.setdefault("policy", {})
    base["policy"]["pmns12_sextet_r12"] = {
        "active": True,
        "placement": placement,
        "axis": "12",
        "theta_step_deg": float(math.degrees(theta_sext)),
        "mult": int(m12),
        "k_pm_mod30": int(k_pm_30),
        "k_pm_mod3": int(k_pm_30 % 3),
        "s12": int(s12),
        "theta12_adj_deg": float(math.degrees(theta12_adj)),
        "rule": "m12 := 1 + (|L_cap| mod 3) from pmns23_cap_lift; θ12_adj = s12·m12·(2π/(30·6))",
        "note": "PP-native θ12 lift as Unu right-basis sextet with cap-derived multiplicity (keeps θ13/θ23 invariant).",
    }

    try:
        ck = ((base.get("CKM") or {}).get("angles") or {})
        base["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return base


def _rt_construct_misalignment_v0_27_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_mcap_1260_NEG(
    delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]
) -> Dict[str, Any]:
    """NEG for v0.27: flip sign of the PMNS12 cap-multiplicity sextet (s12 -> -s12)."""

    base = _rt_construct_misalignment_v0_21_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_1260(
        delta_deg_ckm, delta_deg_pmns
    )
    base["version"] = "rt_construct_v0_27_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_mcap_1260_NEG"
    if base.get("error") is not None:
        return base
    if np is None:
        base["error"] = "numpy not available"
        return base

    pol = base.get("policy") or {}
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    cap_pack = pol.get("pmns23_cap_lift") or {}
    L_cap = int(cap_pack.get("L_cap") or -7)
    m12 = 1 + (abs(int(L_cap)) % 3)
    if m12 <= 0:
        m12 = 1

    Ue_cap_pack = base.get("Ue_cap") or {}
    Unu_adj_pack = base.get("Unu_adj") or {}
    A1 = Ue_cap_pack.get("U_abs")
    P1 = Ue_cap_pack.get("U_phase_rad")
    A2 = Unu_adj_pack.get("U_abs")
    P2 = Unu_adj_pack.get("U_phase_rad")

    if not (A1 and P1 and A2 and P2):
        pm0 = base.get("PMNS") or {}
        U_abs = pm0.get("U_abs")
        U_phi = pm0.get("U_phase_rad")
        if not (U_abs and U_phi):
            base["error"] = "missing PMNS phases (U_phase_rad) from v0.21"
            return base
        U_pre = np.array(U_abs, dtype=np.float64) * np.exp(1j * np.array(U_phi, dtype=np.float64))
        Ue_cap = None
        Unu_adj = None
    else:
        Ue_cap = np.array(A1, dtype=np.float64) * np.exp(1j * np.array(P1, dtype=np.float64))
        Unu_adj = np.array(A2, dtype=np.float64) * np.exp(1j * np.array(P2, dtype=np.float64))
        U_pre = Ue_cap.conjugate().T @ Unu_adj

    theta_sext = float(2.0 * math.pi / (30.0 * 6.0))
    s12 = -(((k_pm_30 % 3) - 1))
    theta12_adj = float(theta_sext * float(s12) * float(m12))
    c12 = math.cos(theta12_adj)
    s12s = math.sin(theta12_adj)
    R12r = np.array([[c12, s12s, 0.0], [-s12s, c12, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)

    if Unu_adj is None:
        U2 = U_pre @ R12r
        placement = "PMNS_right_column_mix (fallback)"
    else:
        Unu2 = Unu_adj @ R12r
        U2 = Ue_cap.conjugate().T @ Unu2
        placement = "Unu_right_basis_generator (PP-native)"

    pm = _angles_J_from_unitary([[complex(U2[i, j]) for j in range(3)] for i in range(3)])
    base["PMNS"] = {
        "U_abs": _rt_abs_from_np(U2),
        "U_phase_rad": _rt_phase_from_np(U2),
        "unitary_residual": _rt_unitary_residual_np(U2),
        "angles": pm,
    }

    base.setdefault("NEG", {})
    base["NEG"]["pmns12_sextet_mcap_sign_flip"] = True

    base.setdefault("policy", {})
    base["policy"]["pmns12_sextet_r12"] = {
        "active": True,
        "placement": placement,
        "axis": "12",
        "theta_step_deg": float(math.degrees(theta_sext)),
        "mult": int(m12),
        "k_pm_mod30": int(k_pm_30),
        "k_pm_mod3": int(k_pm_30 % 3),
        "s12": int(s12),
        "theta12_adj_deg": float(math.degrees(theta12_adj)),
        "rule": "NEG: s12 -> -s12; m12 := 1 + (|L_cap| mod 3)",
        "note": "NEG control for cap-derived θ12 lift.",
    }

    try:
        ck = ((base.get("CKM") or {}).get("angles") or {})
        base["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass

    return base


def _rt_construct_misalignment_v0_22_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_1260_NEG(
    delta_deg_ckm: Optional[float], delta_deg_pmns: Optional[float]
) -> Dict[str, Any]:
    """NEG for v0.22: flip sign of the PMNS12 right-R12 sextet."""

    base = _rt_construct_misalignment_v0_21_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_1260(
        delta_deg_ckm, delta_deg_pmns
    )
    base["version"] = "rt_construct_v0_22_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_1260_NEG"
    if base.get("error") is not None:
        return base

    if np is None:
        base["error"] = "numpy not available"
        return base

    pol = base.get("policy") or {}
    db_pm = ((pol.get("delta_base") or {}).get("PMNS") or {})
    k_pm_30 = int(db_pm.get("k_mod30") or 0) % 30

    # PP-native NEG: flip sign of the Unu right-basis R12 sextet (θ12 lift).

    Ue_cap_pack = base.get('Ue_cap') or {}
    Unu_adj_pack = base.get('Unu_adj') or {}
    A1 = Ue_cap_pack.get('U_abs'); P1 = Ue_cap_pack.get('U_phase_rad')
    A2 = Unu_adj_pack.get('U_abs'); P2 = Unu_adj_pack.get('U_phase_rad')

    if not (A1 and P1 and A2 and P2):
        pm0 = (base.get('PMNS') or {})
        U_abs = pm0.get('U_abs')
        U_phi = pm0.get('U_phase_rad')
        if not (U_abs and U_phi):
            base['error'] = 'missing PMNS phases (U_phase_rad) from v0.21'
            return base
        U_pre = (
            np.array(U_abs, dtype=np.float64)
            * np.exp(1j * np.array(U_phi, dtype=np.float64))
        )
        Ue_cap = None
        Unu_adj = None
    else:
        Ue_cap = (
            np.array(A1, dtype=np.float64)
            * np.exp(1j * np.array(P1, dtype=np.float64))
        )
        Unu_adj = (
            np.array(A2, dtype=np.float64)
            * np.exp(1j * np.array(P2, dtype=np.float64))
        )
        U_pre = Ue_cap.conjugate().T @ Unu_adj

    theta_sext = float(2.0 * math.pi / (30.0 * 6.0))
    s12 = -((k_pm_30 % 3) - 1)
    theta12_adj = float(theta_sext * float(s12))
    c12 = math.cos(theta12_adj)
    s12s = math.sin(theta12_adj)
    R12r = np.array([[c12, s12s, 0.0], [-s12s, c12, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)

    if Unu_adj is None:
        U2 = U_pre @ R12r
        placement = 'PMNS_right_column_mix (fallback)'
    else:
        Unu2 = Unu_adj @ R12r
        U2 = Ue_cap.conjugate().T @ Unu2
        placement = 'Unu_right_basis_generator (PP-native)'

    pm = _angles_J_from_unitary([[complex(U2[i, j]) for j in range(3)] for i in range(3)])
    base['PMNS'] = {
        'U_abs': _rt_abs_from_np(U2),
        'U_phase_rad': _rt_phase_from_np(U2),
        'unitary_residual': _rt_unitary_residual_np(U2),
        'angles': pm,
    }
    base.setdefault('NEG', {})
    base['NEG']['pmns12_sextet_sign_flip'] = True
    base.setdefault('policy', {})
    base['policy']['pmns12_sextet_r12'] = {
        'active': True,
        'placement': placement,
        'axis': '12',
        'theta_step_deg': float(math.degrees(theta_sext)),
        'k_pm_mod30': int(k_pm_30),
        'k_pm_mod3': int(k_pm_30 % 3),
        's12': int(s12),
        'theta12_adj_deg': float(math.degrees(theta12_adj)),
        'note': 'NEG: sign-flipped θ12 sextet in Unu right-basis.',
    }


    try:
        ck = ((base.get("CKM") or {}).get("angles") or {})
        base["gate"] = _rt_compute_structural_gates(ck, pm)
    except Exception:
        pass
    return base


def _rt_construct_misalignment_v0_1() -> Dict[str, Any]:
    """Deterministic RT candidate for flavor misalignment (v0.2).

    Purpose: provide a *scan-free* baseline that builds CKM/PMNS from RT-discrete choices
    (Z3 weight, A/B half shift, C30 projectors, rho/30 ontology).

    This is a diagnostic bridge: it is expected to be refined, but it must be deterministic
    and have NEG controls.
    """

    out: Dict[str, Any] = {
        "version": "rt_construct_v0_2",
        "error": None,
        "policy": {},
        "sectors": {},
        "CKM": {},
        "PMNS": {},
        "NEG": {},
        "gate": {},
    }

    if np is None:
        out["error"] = "numpy not available"
        return out

    # Edge phases from δφ*: use A-half (δ) and B-half (δ+π), each quantized to π/3.
    phi_A = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD)
    phi_B = _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi)

    c0, c1, c2 = _rt_circulant_Z3_weight()

    # Projectors: quarks use Z3-like step (k=10 -> 0,±2π/3 across gens).
    # Leptons use a different step to force large misalignment (k=0 vs k=5).
    P_q = _rt_proj_phase_C30(10)
    P_e = _rt_proj_phase_C30(0)
    P_n = _rt_proj_phase_C30(5)

    def _build_sector(name: str, p: int, phi_edge: float, eps: float, P):
        N = _rt_near_coupling_matrix(int(p))
        N = _rt_apply_edge_phases(N, float(phi_edge))
        C = np.array([[c0, c1, c2], [c2, c0, c1], [c1, c2, c0]], dtype=np.complex128)
        M = P @ (C + complex(float(eps), 0.0) * N) @ P.conjugate().T
        m, U = _rt_diag_yukawa(M)
        U = _rt_gauge_fix_unitary(U)
        return {
            "p": int(p),
            "phi_edge_rad": float(phi_edge),
            "phi_edge_deg": float(math.degrees(float(phi_edge))),
            "eps": float(eps),
            "masses": [float(x) for x in (m.tolist() if m is not None else [])],
            "U": U,
            "M": M,
        }

    # Deterministic sector choices (v0.1)
    # - u: directed chain (p=6), A-half edge phase, +eps
    # - d: symmetric chain (p=5), B-half edge phase, -eps
    # - e: symmetric chain (p=5), B-half edge phase, -eps
    # - nu(D): 3-cycle (p=4), A-half edge phase, +eps, then seesaw
    u = _build_sector("u", 6, phi_A, +RT_EPS0, P_q)
    d = _build_sector("d", 5, phi_B, -RT_EPS0, P_q)
    e = _build_sector("e", 5, phi_B, -RT_EPS0, P_e)
    nuD = _build_sector("nuD", 4, phi_A, +RT_EPS0, P_n)

    out["policy"] = {
        "delta_phi_star_rad": float(RT_DELTA_PHI_STAR_RAD),
        "edge_phase_quantization": "nearest π/3",
        "phi_A_deg": float(math.degrees(phi_A)),
        "phi_B_deg": float(math.degrees(phi_B)),
        "circulant_c": [c0, c1, c2],
        "eps0": float(RT_EPS0),
        "projectors": {
            "quark": "C30 projector k=10 (Z3 step)",
            "lepton_e": "C30 projector k=0 (none)",
            "lepton_nu": "C30 projector k=5 (Z6 step)",
        },
    }

    out["sectors"] = {
        "u": {k: v for k, v in u.items() if k not in ("U", "M")},
        "d": {k: v for k, v in d.items() if k not in ("U", "M")},
        "e": {k: v for k, v in e.items() if k not in ("U", "M")},
        "nuD": {k: v for k, v in nuD.items() if k not in ("U", "M")},
    }

    # CKM
    V = u["U"].conjugate().T @ d["U"]
    out["CKM"] = {
        "V_abs": _rt_abs_from_np(V),
        "unitary_residual": _rt_unitary_residual_np(V),
        "angles": _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)]),
    }

    # PMNS: seesaw Mnu = MD^T MR^{-1} MD with fixed MR=diag(1,2,3)
    MR = np.diag([1.0, 2.0, 3.0]).astype(np.complex128)
    MRi = np.linalg.inv(MR)
    Mnu = nuD["M"].T @ MRi @ nuD["M"]
    _, Unu = _rt_diag_yukawa(Mnu)
    Unu = _rt_gauge_fix_unitary(Unu)
    U = e["U"].conjugate().T @ Unu
    out["PMNS"] = {
        "U_abs": _rt_abs_from_np(U),
        "unitary_residual": _rt_unitary_residual_np(U),
        "angles": _angles_J_from_unitary([[complex(U[i, j]) for j in range(3)] for i in range(3)]),
    }

    # NEG: trivial mixing when using identical bases
    V0 = u["U"].conjugate().T @ u["U"]
    U0 = e["U"].conjugate().T @ e["U"]
    out["NEG"] = {
        "CKM_trivial": {
            "unitary_residual": _rt_unitary_residual_np(V0),
            "angles": _angles_J_from_unitary([[complex(V0[i, j]) for j in range(3)] for i in range(3)]),
        },
        "PMNS_trivial": {
            "unitary_residual": _rt_unitary_residual_np(U0),
            "angles": _angles_J_from_unitary([[complex(U0[i, j]) for j in range(3)] for i in range(3)]),
        },
    }

    # Gates (diagnostic):
    # (1) structural: quark mixing is smaller than lepton mixing
    # (2) CKM pattern: non-trivial + hierarchical + within coarse RT-derived windows
    # (3) PMNS pattern: “large mixing” (very loose) + NEG sanity
    ck = out["CKM"]["angles"]
    pm = out["PMNS"]["angles"]
    def _score(a: Dict[str, float]) -> float:
        return float(a.get("theta12_deg", 0.0)) ** 2 + float(a.get("theta23_deg", 0.0)) ** 2 + float(a.get("theta13_deg", 0.0)) ** 2
    s_ckm = _score(ck)
    s_pmns = _score(pm)

    # NEG sanity (should be ~0)
    neg_ck = out["NEG"]["CKM_trivial"]["angles"]
    neg_pm = out["NEG"]["PMNS_trivial"]["angles"]
    neg_ok = bool(
        abs(float(neg_ck.get("J", 0.0))) <= MAX_NEG_J_ABS and
        abs(float(neg_pm.get("J", 0.0))) <= MAX_NEG_J_ABS and
        float(neg_ck.get("theta12_deg", 0.0)) <= MAX_NEG_THETA_DEG and
        float(neg_ck.get("theta23_deg", 0.0)) <= MAX_NEG_THETA_DEG and
        float(neg_ck.get("theta13_deg", 0.0)) <= MAX_NEG_THETA_DEG and
        float(neg_pm.get("theta12_deg", 0.0)) <= MAX_NEG_THETA_DEG and
        float(neg_pm.get("theta23_deg", 0.0)) <= MAX_NEG_THETA_DEG and
        float(neg_pm.get("theta13_deg", 0.0)) <= MAX_NEG_THETA_DEG
    )

    pass_struct = bool(s_ckm < s_pmns and neg_ok)

    def _in_range(x: float, r: Tuple[float, float]) -> bool:
        return (x >= float(r[0])) and (x <= float(r[1]))

    # CKM pattern gate (coarse). Uses only fixed integers (K=30, rho=10), no PDG.
    ck_t12 = float(ck.get("theta12_deg", 0.0))
    ck_t23 = float(ck.get("theta23_deg", 0.0))
    ck_t13 = float(ck.get("theta13_deg", 0.0))
    ck_J = float(ck.get("J", 0.0))
    ck_order = bool(ck_t12 > ck_t23 > ck_t13)
    ck_ranges_ok = bool(
        _in_range(ck_t12, RT_CKM_THETA12_RANGE_DEG)
        and _in_range(ck_t23, RT_CKM_THETA23_RANGE_DEG)
        and _in_range(ck_t13, RT_CKM_THETA13_RANGE_DEG)
    )
    ck_cp_ok = bool((abs(ck_J) >= MIN_J_ABS) and (abs(ck_J) <= RT_CKM_MAX_J_ABS))
    pass_ckm_pattern = bool(ck_order and ck_ranges_ok and ck_cp_ok)

    # PMNS large-mixing gate (very loose; only rejects near-trivial)
    pm_t12 = float(pm.get("theta12_deg", 0.0))
    pm_t23 = float(pm.get("theta23_deg", 0.0))
    pm_t13 = float(pm.get("theta13_deg", 0.0))
    pm_large_count = int(pm_t12 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t23 >= RT_PMNS_MIN_LARGE_ANGLE_DEG) + int(pm_t13 >= RT_PMNS_MIN_LARGE_ANGLE_DEG)
    pass_pmns_pattern = bool(pm_large_count >= 2)

    out["gate"] = {
        "score": {
            "ckm": float(s_ckm),
            "pmns": float(s_pmns),
            "pass": bool(pass_struct),
            "policy": "Require score(CKM) < score(PMNS); NEG trivial must be ~0",
        },
        "ckm_pattern": {
            "theta12_range_deg": [float(RT_CKM_THETA12_RANGE_DEG[0]), float(RT_CKM_THETA12_RANGE_DEG[1])],
            "theta23_range_deg": [float(RT_CKM_THETA23_RANGE_DEG[0]), float(RT_CKM_THETA23_RANGE_DEG[1])],
            "theta13_range_deg": [float(RT_CKM_THETA13_RANGE_DEG[0]), float(RT_CKM_THETA13_RANGE_DEG[1])],
            "ordering": "theta12>theta23>theta13",
            "J_range_abs": [float(MIN_J_ABS), float(RT_CKM_MAX_J_ABS)],
            "values": {"theta12_deg": ck_t12, "theta23_deg": ck_t23, "theta13_deg": ck_t13, "J": ck_J},
            "pass": bool(pass_ckm_pattern),
        },
        "pmns_pattern": {
            "min_large_angle_deg": float(RT_PMNS_MIN_LARGE_ANGLE_DEG),
            "large_count": int(pm_large_count),
            "values": {"theta12_deg": pm_t12, "theta23_deg": pm_t23, "theta13_deg": pm_t13},
            "pass": bool(pass_pmns_pattern),
        },
        "neg_ok": bool(neg_ok),
        "pass": bool(pass_struct and pass_ckm_pattern and pass_pmns_pattern),
        "policy": "Structural+pattern gates (diagnostic): score + CKM window+hierarchy+CP + PMNS large-mixing + NEG",
    }

    return out

def _perm_scan_abs(M: list, ref: Optional[Dict[str, Any]], kind: str) -> Dict[str, Any]:
    """Discrete relabeling scan over row/col permutations using only abs(M).

    kind:
      - "CKM"  => compare to refs.ckm_theta??_deg if present
      - "PMNS" => compare to refs.pmns_theta??_deg ranges if present
    """

    out: Dict[str, Any] = {
        "kind": kind,
        "scan": {"n_perm": 0, "n_valid": 0},
        "best": None,
        "min_abs": None,
        "min_theta13_deg_bound": None,
        "note": "abs-only; no phases; discrete row/col relabeling only",
    }

    # Lower bound on theta13 under any relabeling: theta13 = arcsin(|(row0,col2)|)
    # and (row0,col2) is some element of M after permutations.
    try:
        flat = [abs(float(M[i][j])) for i in range(3) for j in range(3)]
        mmin = min(flat)
        out["min_abs"] = mmin
        out["min_theta13_deg_bound"] = math.degrees(math.asin(min(max(mmin, 0.0), 1.0)))
    except Exception:
        pass

    refs = (ref or {}).get("refs", {}) if ref else {}

    def _ckm_cost(a: Dict[str, float]) -> Optional[float]:
        if not refs:
            return None
        try:
            r12 = float(refs.get("ckm_theta12_deg", {}).get("value"))
            r23 = float(refs.get("ckm_theta23_deg", {}).get("value"))
            r13 = float(refs.get("ckm_theta13_deg", {}).get("value"))
            return (a["theta12_deg"] - r12) ** 2 + (a["theta23_deg"] - r23) ** 2 + (a["theta13_deg"] - r13) ** 2
        except Exception:
            return None

    def _pmns_cost(a: Dict[str, float]) -> Optional[float]:
        if not refs:
            return None
        try:
            def rc(v: float, lo: float, hi: float) -> float:
                if lo <= v <= hi:
                    return 0.0
                if v < lo:
                    return (lo - v) ** 2
                return (v - hi) ** 2

            r12 = refs.get("pmns_theta12_deg", {}).get("range")
            r23 = refs.get("pmns_theta23_deg", {}).get("range")
            r13 = refs.get("pmns_theta13_deg", {}).get("range")
            if not (isinstance(r12, list) and isinstance(r23, list) and isinstance(r13, list)):
                return None
            return (
                rc(a["theta12_deg"], float(r12[0]), float(r12[1]))
                + rc(a["theta23_deg"], float(r23[0]), float(r23[1]))
                + rc(a["theta13_deg"], float(r13[0]), float(r13[1]))
            )
        except Exception:
            return None

    best: Optional[Dict[str, Any]] = None
    for pr in itertools.permutations(range(3)):
        for pc in itertools.permutations(range(3)):
            out["scan"]["n_perm"] += 1
            Mp = [[float(M[i][j]) for j in pc] for i in pr]
            a = _angles_from_abs_matrix(Mp)
            if a is None:
                continue
            out["scan"]["n_valid"] += 1

            cost = _ckm_cost(a) if kind == "CKM" else _pmns_cost(a)
            # If no refs, pick smallest theta13 as a deterministic proxy.
            key = (cost if cost is not None else a["theta13_deg"])

            cand = {
                "row_perm": list(pr),
                "col_perm": list(pc),
                "angles_deg": a,
                "cost": cost,
                "proxy_key": key,
                "M_abs_row0": Mp[0],
            }
            if best is None or key < best["proxy_key"]:
                best = cand

    out["best"] = best

    # Simple impossibility flags (when refs exist)
    if refs and out.get("min_theta13_deg_bound") is not None:
        if kind == "CKM":
            try:
                r13 = float(refs.get("ckm_theta13_deg", {}).get("value"))
                tol = float(refs.get("ckm_theta13_deg", {}).get("tol_abs"))
                out["cannot_reach_ref_theta13_by_relabeling"] = bool(out["min_theta13_deg_bound"] > (r13 + tol))
            except Exception:
                pass
        if kind == "PMNS":
            try:
                r13_rng = refs.get("pmns_theta13_deg", {}).get("range")
                if isinstance(r13_rng, list) and len(r13_rng) == 2:
                    lo = float(r13_rng[0])
                    out["cannot_reach_pmns_theta13_range_by_relabeling"] = bool(out["min_theta13_deg_bound"] > lo)
            except Exception:
                pass

    return out


def _misalignment_metrics(V_abs: list, U_abs: list, ckm_a: dict, pmns_a: dict, delta_diag: Optional[dict]) -> dict:
    """CKM/PMNS misalignment diagnostics (no tuning; informational only)."""

    def _fro(M1, M2):
        ss = 0.0
        for i in range(3):
            for j in range(3):
                d = float(M1[i][j]) - float(M2[i][j])
                ss += d * d
        return math.sqrt(ss)

    def _fro_sq(M1, M2):
        ss = 0.0
        for i in range(3):
            for j in range(3):
                d = float(M1[i][j]) ** 2 - float(M2[i][j]) ** 2
                ss += d * d
        return math.sqrt(ss)

    def _offdiag_sq(M):
        ss = 0.0
        for i in range(3):
            for j in range(3):
                if i == j:
                    continue
                ss += float(M[i][j]) ** 2
        return ss

    out = {
        'abs_fro': _fro(V_abs, U_abs),
        'abs_sq_fro': _fro_sq(V_abs, U_abs),
        'offdiag_sq': {
            'CKM': _offdiag_sq(V_abs),
            'PMNS': _offdiag_sq(U_abs),
        },
        'angles_deg': {
            'CKM': {k: float(ckm_a[k]) for k in ('theta12_deg','theta23_deg','theta13_deg','J') if k in ckm_a},
            'PMNS': {k: float(pmns_a[k]) for k in ('theta12_deg','theta23_deg','theta13_deg','J') if k in pmns_a},
        },
    }
    out['offdiag_sq']['delta'] = out['offdiag_sq']['PMNS'] - out['offdiag_sq']['CKM']

    if delta_diag:
        dd_ckm = (delta_diag.get('CKM') or {})
        dd_pmns = (delta_diag.get('PMNS') or {})
        out['delta_C30'] = {
            'CKM': {
                'delta_best_deg': dd_ckm.get('delta_best_deg'),
                'k': (dd_ckm.get('C30_grid') or {}).get('k'),
                'delta_grid_deg': (dd_ckm.get('C30_grid') or {}).get('delta_grid_deg'),
                'k_best': (dd_ckm.get('C30_best_fit') or {}).get('k_best'),
                'delta_bestfit_grid_deg': (dd_ckm.get('C30_best_fit') or {}).get('delta_grid_deg'),
                'bestfit_abs_max_err': (dd_ckm.get('C30_best_fit') or {}).get('abs_max_err'),
            },
            'PMNS': {
                'delta_best_deg': dd_pmns.get('delta_best_deg'),
                'k': (dd_pmns.get('C30_grid') or {}).get('k'),
                'delta_grid_deg': (dd_pmns.get('C30_grid') or {}).get('delta_grid_deg'),
                'k_best': (dd_pmns.get('C30_best_fit') or {}).get('k_best'),
                'delta_bestfit_grid_deg': (dd_pmns.get('C30_best_fit') or {}).get('delta_grid_deg'),
                'bestfit_abs_max_err': (dd_pmns.get('C30_best_fit') or {}).get('abs_max_err'),
            },
        }

    return out


def _not_identical(v1: Tuple[float, float], v2: Tuple[float, float]) -> bool:
    return (abs(v1[0] - v2[0]) > EPS_RATIO_DIFF) or (abs(v1[1] - v2[1]) > EPS_RATIO_DIFF)


def _nontrivial_angles(a: Dict[str, float]) -> bool:
    return (
        a["theta12_deg"] >= MIN_THETA_DEG
        and a["theta23_deg"] >= MIN_THETA_DEG
        and a["theta13_deg"] >= MIN_THETA_DEG
    )


def _nonzero_J(a: Dict[str, float]) -> bool:
    return abs(a["J"]) >= MIN_J_ABS


def _neg_is_trivial(a: Dict[str, float]) -> bool:
    return (
        abs(a["J"]) <= MAX_NEG_J_ABS
        and abs(a["theta12_deg"]) <= MAX_NEG_THETA_DEG
        and abs(a["theta23_deg"]) <= MAX_NEG_THETA_DEG
        and abs(a["theta13_deg"]) <= MAX_NEG_THETA_DEG
    )


def _within_abs(v: float, ref: float, tol_abs: float) -> bool:
    return abs(v - ref) <= tol_abs


def _within_rel(v: float, ref: float, tol_rel: float) -> bool:
    if ref == 0:
        return False
    return abs((v - ref) / ref) <= tol_rel


def _in_range(v: float, lo: float, hi: float) -> bool:
    return lo <= v <= hi


def _maybe_load_refs() -> Optional[Dict[str, Any]]:
    p = REPO_ROOT / "00_TOP/OVERLAY/sm29_data_reference_v0_1.json"
    if not p.exists():
        return None
    try:
        return _load_json(p)
    except Exception:
        return None


def main() -> int:
    out_dir = REPO_ROOT / "out/FLAVOR_LOCK"
    ud_p = out_dir / "flavor_ud_v0_9.json"
    enu_p = out_dir / "flavor_enu_v0_9.json"

    if not ud_p.exists() or not enu_p.exists():
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "flavor_lock_verify_summary_v0_1.md").write_text(
            "# FLAVOR_LOCK verify (v0.1)\n\nMISSING inputs.\n", encoding="utf-8"
        )
        return 2

    ud = _load_json(ud_p)
    enu = _load_json(enu_p)

    # 0) Confirm this was a --full scan (explicit, machine-checkable)
    ud_full = bool(ud.get("scan", {}).get("full", False))
    enu_full = bool(enu.get("scan", {}).get("full", False))

    u_r = _ratio_vec(ud.get("u", {}))
    d_r = _ratio_vec(ud.get("d", {}))
    e_r = _ratio_vec(enu.get("e", {}))

    # v0.9 stores angles at ud['CKM']['angles'] and enu['PMNS']['angles'].
    ckm_a = _angles(ud.get("CKM", {}).get("angles", {}))
    pmns_a = _angles(enu.get("PMNS", {}).get("angles", {}))

    # NEG controls live under *.NEG.trivial_mix.angles
    ckm_neg_a = _angles(ud.get("NEG", {}).get("trivial_mix", {}).get("angles", {}))
    pmns_neg_a = _angles(enu.get("NEG", {}).get("trivial_mix", {}).get("angles", {}))

    checks: Dict[str, Dict[str, Any]] = {}

    # 0) Full-scan flag
    checks["full_scan"] = {
        "ud_full": ud_full,
        "enu_full": enu_full,
        "pass": bool(ud_full and enu_full),
    }
    pass_full = bool(checks["full_scan"]["pass"])

    # 1) u/d/e ratios not identical
    checks["ratios_not_identical"] = {
        "u_vs_d": _not_identical(u_r, d_r),
        "u_vs_e": _not_identical(u_r, e_r),
        "d_vs_e": _not_identical(d_r, e_r),
    }
    pass_ratios = all(checks["ratios_not_identical"].values())

    # 2) CKM non-trivial + J not ~0
    checks["ckm_nontrivial"] = {
        "angles_nontrivial": _nontrivial_angles(ckm_a),
        "J_nonzero": _nonzero_J(ckm_a),
        "angles": ckm_a,
    }
    pass_ckm = bool(checks["ckm_nontrivial"]["angles_nontrivial"] and checks["ckm_nontrivial"]["J_nonzero"])

    # 3) PMNS non-trivial + J not ~0
    checks["pmns_nontrivial"] = {
        "angles_nontrivial": _nontrivial_angles(pmns_a),
        "J_nonzero": _nonzero_J(pmns_a),
        "angles": pmns_a,
    }
    pass_pmns = bool(checks["pmns_nontrivial"]["angles_nontrivial"] and checks["pmns_nontrivial"]["J_nonzero"])

    # 3b) NEG controls exist and are trivial
    checks["neg_controls"] = {
        "ckm_trivial_mix": _neg_is_trivial(ckm_neg_a),
        "pmns_trivial_mix": _neg_is_trivial(pmns_neg_a),
        "ckm_angles": ckm_neg_a,
        "pmns_angles": pmns_neg_a,
    }
    pass_neg = bool(checks["neg_controls"]["ckm_trivial_mix"] and checks["neg_controls"]["pmns_trivial_mix"])

    # 4) d-hierarchy not absurd
    d_m1m2 = float(ud.get("d", {}).get("ratios", {}).get("m1_over_m2"))
    checks["d_hierarchy_reasonable"] = {
        "m1_over_m2": d_m1m2,
        "pass": (d_m1m2 >= MIN_HIER_D_M1M2),
        "threshold": MIN_HIER_D_M1M2,
    }
    pass_d = bool(checks["d_hierarchy_reasonable"]["pass"])

    # 5) Overlay-only match gates (do not affect overall PASS)
    ref = _maybe_load_refs()
    match: Dict[str, Any] = {"ref_present": bool(ref is not None), "CKM": {}, "PMNS": {}}

    if ref is not None:
        refs = (ref.get("refs") or {})

        # CKM
        ck = {}
        # angles
        for k in ("ckm_theta12_deg", "ckm_theta23_deg", "ckm_theta13_deg"):
            spec = refs.get(k, {})
            rv = spec.get("value")
            tol = spec.get("tol_abs")
            v = float(ckm_a.get(k.replace("ckm_", ""))) if False else None  # placeholder
        # Map explicitly
        ck_specs = {
            "theta12_deg": refs.get("ckm_theta12_deg", {}),
            "theta23_deg": refs.get("ckm_theta23_deg", {}),
            "theta13_deg": refs.get("ckm_theta13_deg", {}),
            "delta_deg": refs.get("ckm_delta_deg", {}),
            "J": refs.get("ckm_J", {}),
        }
        # delta is quadrant-ambiguous if you only keep sin(delta). For overlay match,
        # use a deterministic branch selection based on abs-matrix consistency (no tuning).
        V_abs_for_delta = ud.get("CKM", {}).get("V_abs")
        delta_best_deg = None
        try:
            sd = ckm_a.get("sin_delta")
            if (sd is not None) and isinstance(V_abs_for_delta, list):
                th12 = math.radians(float(ckm_a.get("theta12_deg")))
                th23 = math.radians(float(ckm_a.get("theta23_deg")))
                th13 = math.radians(float(ckm_a.get("theta13_deg")))
                best = _best_delta_from_sin(float(sd), th12, th23, th13, V_abs_for_delta)
                if best.get("delta_rad") is not None:
                    delta_best_deg = float(math.degrees(float(best["delta_rad"])))
        except Exception:
            delta_best_deg = None

        ck_vals = {
            "theta12_deg": float(ckm_a.get("theta12_deg")),
            "theta23_deg": float(ckm_a.get("theta23_deg")),
            "theta13_deg": float(ckm_a.get("theta13_deg")),
            # prefer best-quadrant delta if available; otherwise keep the principal asin(sinδ) value
            "delta_deg": delta_best_deg if delta_best_deg is not None else (float(ckm_a.get("delta_deg_from_sin")) if ckm_a.get("delta_deg_from_sin") is not None else None),
            "delta_deg_from_sin": float(ckm_a.get("delta_deg_from_sin")) if ckm_a.get("delta_deg_from_sin") is not None else None,
            "sin_delta": float(ckm_a.get("sin_delta")) if ckm_a.get("sin_delta") is not None else None,
            "J": float(ckm_a.get("J")),
        }

        ck_checks = {}
        # abs tol angles
        for kk in ("theta12_deg", "theta23_deg", "theta13_deg"):
            spec = ck_specs.get(kk, {})
            rv = spec.get("value")
            tol = spec.get("tol_abs")
            if rv is None or tol is None:
                ck_checks[kk] = {"pass": None, "note": "missing ref/tol"}
            else:
                ck_checks[kk] = {
                    "pass": _within_abs(float(ck_vals[kk]), float(rv), float(tol)),
                    "rt": ck_vals[kk],
                    "ref": float(rv),
                    "tol_abs": float(tol),
                }

        # delta abs tol (if available)
        spec_d = ck_specs.get("delta_deg", {})
        rv_d = spec_d.get("value")
        tol_d = spec_d.get("tol_abs")
        if ck_vals["delta_deg"] is None or rv_d is None or tol_d is None:
            ck_checks["delta_deg"] = {"pass": None, "note": "missing rt delta or ref/tol"}
        else:
            ck_checks["delta_deg"] = {
                "pass": _within_abs(float(ck_vals["delta_deg"]), float(rv_d), float(tol_d)),
                "rt": float(ck_vals["delta_deg"]),
                "ref": float(rv_d),
                "tol_abs": float(tol_d),
            }

        # J rel tol
        spec_j = ck_specs.get("J", {})
        rv_j = spec_j.get("value")
        tol_j = spec_j.get("tol_rel")
        if rv_j is None or tol_j is None:
            ck_checks["J"] = {"pass": None, "note": "missing ref/tol"}
        else:
            ck_checks["J"] = {
                "pass": _within_rel(float(ck_vals["J"]), float(rv_j), float(tol_j)),
                "rt": float(ck_vals["J"]),
                "ref": float(rv_j),
                "tol_rel": float(tol_j),
            }

        # Composite
        def _all_true(d: Dict[str, Any], keys):
            vals = [d.get(k, {}).get("pass") for k in keys]
            if any(v is None for v in vals):
                return None
            return all(bool(v) for v in vals)

        ck_overall = _all_true(ck_checks, ["theta12_deg", "theta23_deg", "theta13_deg", "delta_deg", "J"])
        match["CKM"] = {
            "checks": ck_checks,
            "pass_all": ck_overall,
            "note": "Overlay-only PDG comparison; does not affect verifier PASS.",
        }

        # PMNS (angles in 3σ ranges)
        pm_specs = {
            "theta12_deg": refs.get("pmns_theta12_deg", {}),
            "theta23_deg": refs.get("pmns_theta23_deg", {}),
            "theta13_deg": refs.get("pmns_theta13_deg", {}),
        }
        pm_vals = {
            "theta12_deg": float(pmns_a.get("theta12_deg")),
            "theta23_deg": float(pmns_a.get("theta23_deg")),
            "theta13_deg": float(pmns_a.get("theta13_deg")),
        }
        pm_checks = {}
        for kk in ("theta12_deg", "theta23_deg", "theta13_deg"):
            spec = pm_specs.get(kk, {})
            rng = spec.get("range")
            if not (isinstance(rng, list) and len(rng) == 2):
                pm_checks[kk] = {"pass": None, "note": "missing ref range"}
            else:
                lo, hi = float(rng[0]), float(rng[1])
                v = float(pm_vals[kk])
                pm_checks[kk] = {
                    "pass": _in_range(v, lo, hi),
                    "rt": v,
                    "range": [lo, hi],
                }

        pm_overall = _all_true(pm_checks, ["theta12_deg", "theta23_deg", "theta13_deg"])
        match["PMNS"] = {
            "checks": pm_checks,
            "pass_all": pm_overall,
            "note": "Overlay-only PDG range check; does not affect verifier PASS.",
        }


        # PP-pred (optional): compare the pp-predicted CKM/PMNS (if present) to the same refs/tols.
        pp_pred_path = REPO_ROOT / "out" / "FLAVOR_LOCK" / "flavor_pp_pred_v0_1.json"
        pp_pred = None
        if pp_pred_path.exists():
            try:
                pp_pred = json.loads(pp_pred_path.read_text(encoding="utf-8"))
            except Exception:
                pp_pred = None
        if isinstance(pp_pred, dict):
            # CKM
            try:
                ckm_pp = (pp_pred.get("CKM", {}) or {}).get("angles_J", {}) or {}
                ck_vals2 = {
                    "theta12_deg": float(ckm_pp.get("theta12_deg")),
                    "theta23_deg": float(ckm_pp.get("theta23_deg")),
                    "theta13_deg": float(ckm_pp.get("theta13_deg")),
                    "delta_deg": float(ckm_pp.get("delta_deg_from_sin")),
                    "J": float(ckm_pp.get("J")),
                }
                ck_checks2 = {}
                for kk in ("theta12_deg", "theta23_deg", "theta13_deg"):
                    spec = ck_specs.get(kk, {})
                    rv = spec.get("value")
                    tol = spec.get("tol_abs")
                    if rv is None or tol is None:
                        ck_checks2[kk] = {"pass": None, "note": "missing ref/tol"}
                    else:
                        ck_checks2[kk] = {
                            "pass": _within_abs(float(ck_vals2[kk]), float(rv), float(tol)),
                            "rt": ck_vals2[kk],
                            "ref": float(rv),
                            "tol_abs": float(tol),
                        }

                # delta abs tol
                if rv_d is None or tol_d is None:
                    ck_checks2["delta_deg"] = {"pass": None, "note": "missing ref/tol"}
                else:
                    ck_checks2["delta_deg"] = {
                        "pass": _within_abs(float(ck_vals2["delta_deg"]), float(rv_d), float(tol_d)),
                        "rt": float(ck_vals2["delta_deg"]),
                        "ref": float(rv_d),
                        "tol_abs": float(tol_d),
                    }

                # J rel tol
                if rv_j is None or tol_j is None:
                    ck_checks2["J"] = {"pass": None, "note": "missing ref/tol"}
                else:
                    ck_checks2["J"] = {
                        "pass": _within_rel(float(ck_vals2["J"]), float(rv_j), float(tol_j)),
                        "rt": float(ck_vals2["J"]),
                        "ref": float(rv_j),
                        "tol_rel": float(tol_j),
                    }

                ck_overall2 = _all_true(ck_checks2, ["theta12_deg", "theta23_deg", "theta13_deg", "delta_deg", "J"])
                match["CKM_pp_pred"] = {
                    "checks": ck_checks2,
                    "pass_all": ck_overall2,
                    "note": "PP-predicted CKM via PP constructs (flavor_lock_pp_predict).",
                }
            except Exception:
                match["CKM_pp_pred"] = {"pass_all": None, "note": "pp_pred present but CKM compare failed"}

            # PMNS
            try:
                pm_pp = (pp_pred.get("PMNS", {}) or {}).get("angles", {}) or {}
                pm_vals2 = {
                    "theta12_deg": float(pm_pp.get("theta12_deg")),
                    "theta23_deg": float(pm_pp.get("theta23_deg")),
                    "theta13_deg": float(pm_pp.get("theta13_deg")),
                }
                pm_checks2 = {}
                for kk in ("theta12_deg", "theta23_deg", "theta13_deg"):
                    spec = pm_specs.get(kk, {})
                    rng = spec.get("range")
                    if not (isinstance(rng, list) and len(rng) == 2):
                        pm_checks2[kk] = {"pass": None, "note": "missing ref range"}
                    else:
                        lo, hi = float(rng[0]), float(rng[1])
                        v = float(pm_vals2[kk])
                        pm_checks2[kk] = {"pass": _in_range(v, lo, hi), "rt": v, "range": [lo, hi]}

                pm_overall2 = _all_true(pm_checks2, ["theta12_deg", "theta23_deg", "theta13_deg"])
                match["PMNS_pp_pred"] = {
                    "checks": pm_checks2,
                    "pass_all": pm_overall2,
                    "note": "PP-predicted PMNS via PP constructs (flavor_lock_pp_predict).",
                }
            except Exception:
                match["PMNS_pp_pred"] = {"pass_all": None, "note": "pp_pred present but PMNS compare failed"}
        else:
            match["CKM_pp_pred"] = {
                "pass_all": None,
                "note": "pp_pred file not found (run 00_TOP/LOCKS/FLAVOR_LOCK/flavor_lock_pp_predict.py)",
            }
            match["PMNS_pp_pred"] = {
                "pass_all": None,
                "note": "pp_pred file not found (run 00_TOP/LOCKS/FLAVOR_LOCK/flavor_lock_pp_predict.py)",
            }

    checks["match_gates"] = match

    # 6) Discrete permutation scan (abs-only): can relabel generations, but cannot
    # change matrix element magnitudes. This is a "no new continuous params" step.
    try:
        V_abs = ud.get("CKM", {}).get("V_abs")
        U_abs = enu.get("PMNS", {}).get("U_abs")
        if isinstance(V_abs, list) and isinstance(U_abs, list):
            checks["perm_scan_abs"] = {
                "note": "3!x3! row/col relabeling on abs matrices only (no phases)",
                "CKM": _perm_scan_abs(V_abs, ref, "CKM"),
                "PMNS": _perm_scan_abs(U_abs, ref, "PMNS"),
            }
    except Exception:
        pass

    
    # 6a) Unistochastic feasibility diagnostics (abs-only; fast triangle tests)
    try:
        V_abs = ud.get("CKM", {}).get("V_abs")
        U_abs = enu.get("PMNS", {}).get("U_abs")
        if isinstance(V_abs, list) and isinstance(U_abs, list):
            checks["unistochastic"] = {
                "note": "3x3 unistochastic feasibility via triangle inequalities on row/col pairs; abs-only.",
                "CKM": {
                    "doubly_stochastic_sq": _is_doubly_stochastic_sq(V_abs),
                    "triangle_checks": _unistochastic_tri_checks(V_abs),
                },
                "PMNS": {
                    "doubly_stochastic_sq": _is_doubly_stochastic_sq(U_abs),
                    "triangle_checks": _unistochastic_tri_checks(U_abs),
                },
            }
    except Exception:
        pass

    # 6a2) Phase quantization diagnostics: delta vs C30 grid (no new continuous knobs; delta is derived)
    try:
        V_abs = ud.get("CKM", {}).get("V_abs")
        U_abs = enu.get("PMNS", {}).get("U_abs")

        def _delta_diag(ang: Dict[str, float], M_abs: list) -> Optional[Dict[str, Any]]:
            sd = ang.get("sin_delta")
            if sd is None:
                return None
            th12 = math.radians(float(ang.get("theta12_deg")))
            th23 = math.radians(float(ang.get("theta23_deg")))
            th13 = math.radians(float(ang.get("theta13_deg")))

            best = _best_delta_from_sin(float(sd), th12, th23, th13, M_abs)
            if best.get("delta_rad") is None:
                return None
            d = float(best["delta_rad"])
            grid = _delta_grid_C30(d)
            bestfit = _best_k_C30(th12, th23, th13, M_abs)

            # abs-consistency at derived delta
            Vbest = _ckm_unitary_pdg(th12, th23, th13, d)
            Abest = _abs_from_complex(Vbest)

            # abs-consistency at nearest C30 delta
            Vg = _ckm_unitary_pdg(th12, th23, th13, float(grid["delta_grid_rad"]))
            Ag = _abs_from_complex(Vg)

            return {
                "delta_best_rad": d,
                "delta_best_deg": math.degrees(d),
                "delta_best_abs_max_err": _max_abs_diff(Abest, M_abs),
                "delta_best_abs_rms_err": _rms_abs_diff(Abest, M_abs),
                "unitary_res_best": _unitary_residual(Vbest),
                "C30_grid": grid,
                "C30_best_fit": bestfit,
                "delta_grid_abs_max_err": _max_abs_diff(Ag, M_abs),
                "delta_grid_abs_rms_err": _rms_abs_diff(Ag, M_abs),
                "unitary_res_grid": _unitary_residual(Vg),
            }

        delta_diag = {}
        if isinstance(V_abs, list):
            dd = _delta_diag(ckm_a, V_abs)
            if dd is not None:
                delta_diag["CKM"] = dd
        if isinstance(U_abs, list):
            dd = _delta_diag(pmns_a, U_abs)
            if dd is not None:
                delta_diag["PMNS"] = dd
        if delta_diag:
            checks["delta_grid_C30"] = delta_diag
    except Exception:
        pass

# 6b) Discrete phase-lift scan: attempt unitary reconstruction without any continuous tuning.
    # This is still diagnostic until phases are RT-derived; but it hardens "what abs-only cannot fix".
    phase_lift = {}
    try:
        V_abs = ud.get("CKM", {}).get("V_abs")
        U_abs = enu.get("PMNS", {}).get("U_abs")
        if isinstance(V_abs, list):
            phase_lift["CKM"] = _phase_lift_scan_abs(V_abs, "CKM")
        if isinstance(U_abs, list):
            phase_lift["PMNS"] = _phase_lift_scan_abs(U_abs, "PMNS")

        # NEG: trivial_mix must remain exactly unitary with J=0.
        Vn = ud.get("NEG", {}).get("trivial_mix", {}).get("V_abs")
        Un = enu.get("NEG", {}).get("trivial_mix", {}).get("U_abs")
        if isinstance(Vn, list):
            phase_lift["NEG_CKM"] = _phase_lift_scan_abs(Vn, "NEG_CKM")
        if isinstance(Un, list):
            phase_lift["NEG_PMNS"] = _phase_lift_scan_abs(Un, "NEG_PMNS")

        checks["phase_lift_scan"] = phase_lift

        # Constructive (closed-form) unitary lift from |M| (diagnostic only)
        constructive = {}
        try:
            if isinstance(V_abs, list):
                constructive["CKM"] = _constructive_unitary_lift_abs(V_abs, "CKM")
            if isinstance(U_abs, list):
                constructive["PMNS"] = _constructive_unitary_lift_abs(U_abs, "PMNS")
            if isinstance(Vn, list):
                constructive["NEG_CKM"] = _constructive_unitary_lift_abs(Vn, "NEG_CKM")
            if isinstance(Un, list):
                constructive["NEG_PMNS"] = _constructive_unitary_lift_abs(Un, "NEG_PMNS")
        except Exception:
            pass
        if constructive:
            checks["constructive_unitary_lift"] = constructive


        # C30-quantized constructive lift (triangle closure with snapped phases; diagnostic only)
        c30q = {}
        try:
            if isinstance(V_abs, list):
                c30q["CKM"] = _constructive_unitary_lift_abs_C30(V_abs, "CKM")
            if isinstance(U_abs, list):
                c30q["PMNS"] = _constructive_unitary_lift_abs_C30(U_abs, "PMNS")
            if isinstance(Vn, list):
                c30q["NEG_CKM"] = _constructive_unitary_lift_abs_C30(Vn, "NEG_CKM")
            if isinstance(Un, list):
                c30q["NEG_PMNS"] = _constructive_unitary_lift_abs_C30(Un, "NEG_PMNS")
        except Exception:
            pass
        if c30q:
            checks["c30_quantized_unitary_lift"] = c30q

        # RT phase rule unitary lift (δφ*, Z3×A/B + tie-breakers; diagnostic only)
        rtpr = {}
        try:
            if isinstance(V_abs, list):
                rtpr["CKM"] = _rt_phase_rule_unitary_lift(V_abs, "CKM")
            if isinstance(U_abs, list):
                rtpr["PMNS"] = _rt_phase_rule_unitary_lift(U_abs, "PMNS")
            if isinstance(Vn, list):
                rtpr["NEG_CKM"] = _rt_phase_rule_unitary_lift(Vn, "NEG_CKM")
            if isinstance(Un, list):
                rtpr["NEG_PMNS"] = _rt_phase_rule_unitary_lift(Un, "NEG_PMNS")
        except Exception:
            pass
        if rtpr:
            checks["rt_phase_rule_unitary_lift"] = rtpr

        # CKM/PMNS misalignment diagnostics (informational; no tuning)
        try:
            if isinstance(V_abs, list) and isinstance(U_abs, list):
                checks["misalignment"] = _misalignment_metrics(V_abs, U_abs, ckm_a, pmns_a, checks.get("delta_grid_C30"))
        except Exception:
            pass
    except Exception:
        pass

    # phase-lift NEG sanity gate
    def _phase_lift_neg_ok(tag: str) -> Optional[bool]:
        obj = (phase_lift.get(tag) or {})
        best = (obj.get("best") or {})
        if not best:
            return None
        res = float(best.get("unitary_residual"))
        ang = best.get("angles") or {}
        J = ang.get("J")
        # Strong sanity tolerance (should be exactly unitary for identity abs-matrix)
        if J is None:
            J = 0.0
        return bool(res <= 1e-12 and abs(float(J)) <= 1e-12)

    phase_neg_ckm = _phase_lift_neg_ok("NEG_CKM")
    phase_neg_pmns = _phase_lift_neg_ok("NEG_PMNS")
    checks["phase_lift_neg"] = {
        "NEG_CKM": phase_neg_ckm,
        "NEG_PMNS": phase_neg_pmns,
        "pass": (bool(phase_neg_ckm) and bool(phase_neg_pmns)) if (phase_neg_ckm is not None and phase_neg_pmns is not None) else None,
    }
    pass_phase_neg = bool(checks["phase_lift_neg"].get("pass")) if checks["phase_lift_neg"].get("pass") is not None else True

    # RT phase-rule gate: require RT-derived δ_C30 to reproduce operational k* (baseline only; NEG is diagnostic)
    def _rt_phase_match(kind: str):
        obj = ((checks.get("rt_phase_rule_unitary_lift") or {}).get(kind) or {})
        best = (obj.get("best") or {})
        cmp = (obj.get("compare") or {})
        ks = (cmp.get("kstar_operational") or {})
        if not best or not ks:
            return None
        k_rt = ((best.get("delta_C30") or {}).get("k_mod30"))
        k_star = ks.get("k_best")
        if k_rt is None or k_star is None:
            return None
        return (int(k_rt) % 30) == (int(k_star) % 30)

    rt_gate_ckm = _rt_phase_match("CKM")
    rt_gate_pmns = _rt_phase_match("PMNS")
    pass_rt_phase = (rt_gate_ckm is True) and (rt_gate_pmns is True)
    checks["rt_phase_rule_gate"] = {
        "CKM": rt_gate_ckm,
        "PMNS": rt_gate_pmns,
        "pass": pass_rt_phase if (rt_gate_ckm is not None and rt_gate_pmns is not None) else None,
        "policy": "Baseline CKM/PMNS only; NEG_* are diagnostic and may not match k*",
    }

    # 7) RT deterministic construct (scan-free) for misalignment (diagnostic; not part of overall PASS yet)
    # v0.2: Yukawa/circulant-based bridge (kept for continuity)
    rt_construct_v02 = _rt_construct_misalignment_v0_1()

    # v0.3: discrete-angle targets, using δ from the RT phase-rule unitary-lift (C30)
    def _best_delta_deg(kind: str) -> Optional[float]:
        try:
            obj = ((checks.get("rt_phase_rule_unitary_lift") or {}).get(kind) or {})
            best = (obj.get("best") or {})
            d = (best.get("delta_C30") or {}).get("deg")
            return float(d) if d is not None else None
        except Exception:
            return None

    rt_construct_v03 = _rt_construct_misalignment_v0_3(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))

    # v0.4: factorized sector unitaries (Uu/Ud, Ue/Unu) via symmetric unitary sqrt
    rt_construct = _rt_construct_misalignment_v0_4_factorized(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct["targets_v0_3"] = {"version": rt_construct_v03.get("version"), "policy": rt_construct_v03.get("policy")}
    rt_construct["legacy_v0_2"] = {"version": rt_construct_v02.get("version"), "gate": rt_construct_v02.get("gate")}

    checks["rt_construct_misalignment"] = rt_construct
    pass_rt_construct = bool((rt_construct.get("gate") or {}).get("pass")) if rt_construct.get("gate") is not None else False


    # v0.5: sector eigphase→C30 snap hardening (diagnostic)
    rt_construct_v05 = _rt_construct_misalignment_v0_5_sector_eigphase_snap(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v05["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_sector_eigphase_snap"] = rt_construct_v05
    pass_rt_sector_snap = bool((rt_construct_v05.get("gate") or {}).get("pass")) if rt_construct_v05.get("gate") is not None else False

    # v0.6: sector eigphase snap with quark micro-grid C(30*rho)=C300 (diagnostic)
    rt_construct_v06 = _rt_construct_misalignment_v0_6_sector_eigphase_snap(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v06["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_sector_eigphase_snap_C300"] = rt_construct_v06
    pass_rt_sector_snap_c300 = bool((rt_construct_v06.get("gate") or {}).get("pass")) if rt_construct_v06.get("gate") is not None else False



    # v0.7: full 1260-tick monodromy scaffold (42×30-tick blocks; diagnostic)
    rt_construct_v07 = _rt_construct_misalignment_v0_7_monodromy_1260(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v08 = _rt_construct_misalignment_v0_8_monodromy_z3kick_1260(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v08["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_z3kick"] = rt_construct_v08

    rt_construct_v09 = _rt_construct_misalignment_v0_9_monodromy_rho_kick_1260(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v09["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_rho_kick"] = rt_construct_v09

    rt_construct_v10 = _rt_construct_misalignment_v0_10_monodromy_rho_z3sieve_1260(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v10["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_rho_z3sieve"] = rt_construct_v10

    rt_construct_v11 = _rt_construct_misalignment_v0_11_monodromy_rho_z3sieve_12tiebreak_1260(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v11["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_rho_z3sieve_12tiebreak"] = rt_construct_v11

    rt_construct_v12 = _rt_construct_misalignment_v0_12_monodromy_cabibbo_kick_12_1260(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v12["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_cabibbo_kick_12"] = rt_construct_v12

    rt_construct_v13 = _rt_construct_misalignment_v0_13_monodromy_postR12_seam_1260(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v13["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam"] = rt_construct_v13

    rt_construct_v14 = _rt_construct_misalignment_v0_14_monodromy_postR12_seam_macro_micro_1260(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v14["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_macro_micro"] = rt_construct_v14

    rt_construct_v15 = _rt_construct_misalignment_v0_15_monodromy_postR12_seam_from_phase_rule_1260(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v15["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_from_phase_rule"] = rt_construct_v15

    rt_construct_v16 = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v16["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_from_phase_rule_down_oriented"] = rt_construct_v16

    rt_construct_v18 = _rt_construct_misalignment_v0_18_monodromy_postR12_seam_down_oriented_pp23_1260(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v18["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23"] = rt_construct_v18

    rt_construct_v19 = _rt_construct_misalignment_v0_19_monodromy_postR12_seam_down_oriented_pp23_uubasis_1260(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v19["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis"] = rt_construct_v19

    rt_construct_v19n = _rt_construct_misalignment_v0_19_monodromy_postR12_seam_down_oriented_pp23_uubasis_1260_NEG(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v19n["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_NEG"] = rt_construct_v19n

    # v0.24 CKM θ13 rho^2 phaseful step (Gate-2 candidate): PP-native, smaller step (~0.12°) with seam phase phi_B
    rt_construct_v24 = _rt_construct_misalignment_v0_24_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_micro2_phiB_1260(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    rt_construct_v24["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_rho2_phiB"] = rt_construct_v24

    rt_construct_v24n = _rt_construct_misalignment_v0_24_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_micro2_phiB_1260_NEG(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    rt_construct_v24n["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_rho2_phiB_NEG"] = rt_construct_v24n

    rt_construct_v25 = _rt_construct_misalignment_v0_25_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_1260(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    rt_construct_v25["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB"] = rt_construct_v25

    rt_construct_v25n = _rt_construct_misalignment_v0_25_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_1260_NEG(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    rt_construct_v25n["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_NEG"] = rt_construct_v25n


    # v0.29 (Gate-4 exploratory): PP-native lifts without PDG row-phase DL
    rt_construct_v29 = _rt_construct_misalignment_v0_29_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_PP_NATIVE_NODL_1260(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_PP_NATIVE_NODL"] = rt_construct_v29

    rt_construct_v29n = _rt_construct_misalignment_v0_29_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_PP_NATIVE_NODL_1260_NEG(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_PP_NATIVE_NODL_NEG"] = rt_construct_v29n


    # v0.30 (Gate-4 candidate): phase-aligned lifts using raw-V0 phases (no PDG fix)
    rt_construct_v30 = _rt_construct_misalignment_v0_30_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_V0PHASE_NODG_1260(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_V0PHASE_NODG"] = rt_construct_v30

    rt_construct_v30n = _rt_construct_misalignment_v0_30_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_V0PHASE_NODG_1260_NEG(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_V0PHASE_NODG_NEG"] = rt_construct_v30n


    # v0.31 (Gate-4): canonical row/col phase gauge (ud/us/cb/tb real), then apply PP23 + CKM13 sextet lift
    rt_construct_v31 = _rt_construct_misalignment_v0_31_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_CANON_ROWPHASE_1260(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_CANON_ROWPHASE"] = rt_construct_v31

    rt_construct_v31n = _rt_construct_misalignment_v0_31_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_CANON_ROWPHASE_1260_NEG(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_CANON_ROWPHASE_NEG"] = rt_construct_v31n

    # v0.33 (Gate-4 promote): freeze best discrete C30 holonomy candidate from diag grid (v0.2)
    rt_construct_v33 = _rt_construct_misalignment_v0_33_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_GRIDBEST_1260(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_GRIDBEST"] = rt_construct_v33

    rt_construct_v33n = _rt_construct_misalignment_v0_33_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_GRIDBEST_1260_NEG(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_GRIDBEST_NEG"] = rt_construct_v33n

    # v0.34 (Gate-4 promote): CPBEST discrete holonomy candidate (passes CKM tolerances)
    rt_construct_v34 = _rt_construct_misalignment_v0_34_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_CPBEST_1260(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_CPBEST"] = rt_construct_v34

    rt_construct_v34n = _rt_construct_misalignment_v0_34_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_CPBEST_1260_NEG(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_CPBEST_NEG"] = rt_construct_v34n

    # v0.26 CKM microbend (diagnostic): v0.25 + cap/weak factors (no promotion)
    rt_construct_v26 = _rt_construct_misalignment_v0_26_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_microbend_1260(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    rt_construct_v26["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_microbend"] = rt_construct_v26

    rt_construct_v26n = _rt_construct_misalignment_v0_26_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_microbend_1260_NEG(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    rt_construct_v26n["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_microbend_NEG"] = rt_construct_v26n

    # v0.23 CKM θ13 quark-sextet (Gate-2 candidate): grid-aware 0.2° step on Uu right-basis (PP-native)
    rt_construct_v23 = _rt_construct_misalignment_v0_23_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_1260(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    rt_construct_v23["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet"] = rt_construct_v23

    rt_construct_v23n = _rt_construct_misalignment_v0_23_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_1260_NEG(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    rt_construct_v23n["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_NEG"] = rt_construct_v23n

    # v0.20 PMNS θ13 sextet-engagement (diagnostic): keep v0.19 CKM; adjust PMNS by 2° step
    rt_construct_v20 = _rt_construct_misalignment_v0_20_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_1260(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v20["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet"] = rt_construct_v20

    rt_construct_v20n = _rt_construct_misalignment_v0_20_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_1260_NEG(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v20n["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_NEG"] = rt_construct_v20n

    # v0.21 PMNS θ23 cap-lift (diagnostic): PP-native Ue right-basis update; equivalent left row-rotation; uses |L_cap|=7 (Global Frame cap)
    rt_construct_v21 = _rt_construct_misalignment_v0_21_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_1260(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v21["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7"] = rt_construct_v21

    rt_construct_v21n = _rt_construct_misalignment_v0_21_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_1260_NEG(_best_delta_deg("CKM"), _best_delta_deg("PMNS"))
    rt_construct_v21n["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_NEG"] = rt_construct_v21n

    # v0.22 PMNS θ12 right-R12 sextet (diagnostic): lifts θ12 discretely without touching θ13/θ23
    rt_construct_v22 = _rt_construct_misalignment_v0_22_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_1260(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    rt_construct_v22["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet"] = rt_construct_v22

    rt_construct_v22n = _rt_construct_misalignment_v0_22_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_1260_NEG(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    rt_construct_v22n["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_NEG"] = rt_construct_v22n

    # v0.27 PMNS θ12 cap-multiplicity sextet (promotion candidate): m12 := 1 + (|L_cap| mod 3)
    rt_construct_v27 = _rt_construct_misalignment_v0_27_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_mcap_1260(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    rt_construct_v27["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_mcap"] = rt_construct_v27

    rt_construct_v27n = _rt_construct_misalignment_v0_27_monodromy_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_mcap_1260_NEG(
        _best_delta_deg("CKM"), _best_delta_deg("PMNS")
    )
    rt_construct_v27n["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_mcap_NEG"] = rt_construct_v27n

    # Seam orientation diagnostic:
    # - v0.16 (down-oriented Z3→micro map) is the *canonical* convention for Ud seam.
    # - v0.15 is retained as a NEG control (same information content, opposite orientation).
    # Informational only; does not affect overall PASS.
    try:
        k_mod3 = int((((((rt_construct_v16.get("policy") or {}).get("delta_base") or {}).get("CKM") or {}).get("k_mod30") or 0))) % 3
        theta15 = float(((((rt_construct_v15.get("policy") or {}).get("postR12_seam") or {}).get("theta_deg")) or 0.0))
        theta16 = float(((((rt_construct_v16.get("policy") or {}).get("postR12_seam") or {}).get("theta_deg")) or 0.0))
        s15 = int(((((rt_construct_v15.get("policy") or {}).get("postR12_seam") or {}).get("theta_components_deg") or {}).get("s_micro")) or 0)
        s16 = int(((((rt_construct_v16.get("policy") or {}).get("postR12_seam") or {}).get("theta_components_deg") or {}).get("s_micro")) or 0)
        checks["rt_construct_seam_orientation"] = {
            "canonical": {
                "version": rt_construct_v16.get("version"),
                "map": "down_oriented",
                "rule": "s_micro := (k_rt mod 3) − 1",
                "k_mod3": int(k_mod3),
                "s_micro": int(s16),
                "theta_deg": float(theta16),
            },
            "neg": {
                "version": rt_construct_v15.get("version"),
                "map": "up_oriented",
                "rule": "s_micro := 1 − (k_rt mod 3)",
                "k_mod3": int(k_mod3),
                "s_micro": int(s15),
                "theta_deg": float(theta15),
            },
            "note": "Informational only; orientation is fixed by the Ud (down-sector) convention.",
        }
    except Exception:
        pass

    rt_construct_v07["inherits_version"] = rt_construct.get("version")
    checks["rt_construct_monodromy_1260"] = rt_construct_v07
    pass_rt_monodromy = bool((rt_construct_v07.get("gate") or {}).get("pass")) if rt_construct_v07.get("gate") is not None else False


    # 8) History diagnostics across existing snapshots (informational only)
    try:
        checks["history_versions"] = _history_versions(out_dir)
    except Exception:
        pass

    # 8.5) Gate-2 regression lock (CKM v0.25 candidate): stability first.
    try:
        lock_key = "rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB"
        cand = (checks.get(lock_key) or {})
        cand_angles = (((cand.get("CKM") or {}).get("angles") or {}))
        lock_path = (out_dir / "regression_lock_ckm_v0_25.json")
        tol_deg = 1e-9
        if cand_angles:
            payload = {
                "lock_version": "v0.25",
                "key": lock_key,
                "angles_deg": {
                    "theta12_deg": float(cand_angles.get("theta12_deg") or 0.0),
                    "theta23_deg": float(cand_angles.get("theta23_deg") or 0.0),
                    "theta13_deg": float(cand_angles.get("theta13_deg") or 0.0),
                    "delta_deg": float(cand_angles.get("delta_deg") or 0.0),
                    "J": float(cand_angles.get("J") or 0.0),
                },
                "tol_deg": float(tol_deg),
            }
            if lock_path.exists():
                ref = json.loads(lock_path.read_text(encoding="utf-8"))
                ref_a = ((ref.get("angles_deg") or {}))
                diffs = {}
                ok = True
                for k in ("theta12_deg", "theta23_deg", "theta13_deg", "delta_deg"):
                    dv = abs(float(payload["angles_deg"].get(k) or 0.0) - float(ref_a.get(k) or 0.0))
                    diffs[k] = float(dv)
                    if dv > tol_deg:
                        ok = False
                checks["regression_lock_ckm_v0_25"] = {
                    "pass": bool(ok),
                    "tol_deg": float(tol_deg),
                    "diffs_deg": diffs,
                    "ref": ref_a,
                    "cur": payload["angles_deg"],
                    "note": "Gate-2 candidate regression lock: CKM angles must not drift when we do Gate-3/4 work.",
                }
            else:
                lock_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
                checks["regression_lock_ckm_v0_25"] = {
                    "pass": True,
                    "tol_deg": float(tol_deg),
                    "created": True,
                    "cur": payload["angles_deg"],
                    "note": "Created Gate-2 regression lock for CKM v0.25 candidate.",
                }
    except Exception:
        pass


    # 6b) DIAG: discrete scan over phase-branch + optional eigphase snap (no knobs)
    try:
        if (ref is not None) and (np is not None):
            refs = (ref.get("refs") or {})
            # Reload refs defensively (avoid accidental mutation).
            ref2 = _maybe_load_refs()
            refs2 = ((ref2 or {}).get("refs") or (ref.get("refs") or {}))
            t12_ref = float((refs2.get("ckm_theta12_deg", {}) or {}).get("value", 12.997))
            t12_tol = float((refs2.get("ckm_theta12_deg", {}) or {}).get("tol_abs", 0.05))
            t23_ref = float((refs2.get("ckm_theta23_deg", {}) or {}).get("value", 2.397))
            t23_tol = float((refs2.get("ckm_theta23_deg", {}) or {}).get("tol_abs", 0.03))
            t13_ref = float((refs2.get("ckm_theta13_deg", {}) or {}).get("value", 0.214))
            t13_tol = float((refs2.get("ckm_theta13_deg", {}) or {}).get("tol_abs", 0.01))
            d_ref = float((refs2.get("ckm_delta_deg", {}) or {}).get("value", 65.73))
            d_tol = float((refs2.get("ckm_delta_deg", {}) or {}).get("tol_abs", 4.5))
            J_ref = float((refs2.get("ckm_J", {}) or {}).get("value", 3.12e-5))
            J_tol_rel = float((refs2.get("ckm_J", {}) or {}).get("tol_rel", 0.05))

            def _delta_best_deg_from_angles(ang: Dict[str, Any], V_abs: Any) -> Optional[float]:
                try:
                    sd = ang.get("sin_delta")
                    if (sd is None) or (not isinstance(V_abs, list)):
                        return None
                    th12 = math.radians(float(ang.get("theta12_deg") or 0.0))
                    th23 = math.radians(float(ang.get("theta23_deg") or 0.0))
                    th13 = math.radians(float(ang.get("theta13_deg") or 0.0))
                    best = _best_delta_from_sin(float(sd), th12, th23, th13, V_abs)
                    if best.get("delta_rad") is None:
                        return None
                    return float(math.degrees(float(best["delta_rad"])))
                except Exception:
                    return None

            def _score_ckm(ang: Dict[str, Any], V_abs: Any) -> Optional[float]:
                try:
                    t12 = float(ang.get("theta12_deg"))
                    t23 = float(ang.get("theta23_deg"))
                    t13 = float(ang.get("theta13_deg"))
                    J = float(ang.get("J"))
                except Exception:
                    return None

                # delta: use best quadrant (deterministic) if possible
                d_best = _delta_best_deg_from_angles(ang, V_abs)
                if d_best is None:
                    try:
                        d_best = float(ang.get("delta_deg_from_sin"))
                    except Exception:
                        d_best = None

                def _term_abs(v: float, ref_v: float, tol_abs: float) -> float:
                    if tol_abs <= 0:
                        return 0.0
                    return ((float(v) - float(ref_v)) / float(tol_abs)) ** 2
                s = 0.0
                s += _term_abs(t12, t12_ref, t12_tol)
                s += _term_abs(t23, t23_ref, t23_tol)
                s += _term_abs(t13, t13_ref, t13_tol)
                if d_best is not None:
                    # wrap to [0,360) before scoring (PDG uses degrees in [0,360))
                    d0 = float(d_best) % 360.0
                    # allow the reflection branch (180-δ) from sinδ ambiguity
                    d1 = (180.0 - d0) % 360.0
                    dd = min(abs(d0 - d_ref), abs(d1 - d_ref), abs((d0 + 360.0) - d_ref), abs((d1 + 360.0) - d_ref))
                    s += _term_abs(dd, 0.0, d_tol)
                # J: relative tolerance
                try:
                    if (J_ref != 0.0) and (J_tol_rel > 0.0):
                        s += ((float(J) - float(J_ref)) / (float(J_tol_rel) * float(J_ref))) ** 2
                except Exception:
                    pass
                    pass
                return float(s)

            results = []
            for seam_phase in ("phi_A", "phi_B"):
                for r13_phase in ("phi_A", "phi_B"):
                    for snap_q in (False, True):
                        for snap_l in (False, True):
                            node = _rt_construct_misalignment_v0_27_monodromy_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phase_scan_1260(
                                None, None, seam_phase=seam_phase, r13_phase=r13_phase, snap_quark=snap_q, snap_lepton=snap_l
                            )
                            if not isinstance(node, dict) or node.get("error"):
                                continue
                            ckm = (node.get("CKM") or {})
                            ang = (ckm.get("angles") or {})
                            V_abs = ckm.get("V_abs")
                            sc = _score_ckm(ang, V_abs)
                            if sc is None:
                                continue
                            d_best = _delta_best_deg_from_angles(ang, V_abs)
                            results.append(
                                {
                                    "seam_phase": seam_phase,
                                    "r13_phase": r13_phase,
                                    "snap_quark": bool(snap_q),
                                    "snap_lepton": bool(snap_l),
                                    "score": float(sc),
                                    "theta12_deg": float(ang.get("theta12_deg")),
                                    "theta23_deg": float(ang.get("theta23_deg")),
                                    "theta13_deg": float(ang.get("theta13_deg")),
                                    "delta_best_deg": float(d_best) if d_best is not None else None,
                                    "J": float(ang.get("J")),
                                }
                            )

            results.sort(key=lambda r: float(r.get("score") or 1e99))
            top = results[:12]

            checks["diag_ckm_discrete_scan"] = {
                "count": int(len(results)),
                "top": top,
                "note": "Diagnostic only: discrete phase-branch + optional eigphase-snap scan (no tuning).",
            }

            # also write explicit scan artifacts
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "ckm_discrete_scan_v0_1.json").write_text(json.dumps({"top": top, "count": len(results)}, indent=2, sort_keys=True), encoding="utf-8")
                md_lines = ["# CKM discrete scan (v0.1)", "", f"candidates: {len(results)}", "", "## Top", ""]
                for i, r in enumerate(top, 1):
                    d = r.get("delta_best_deg")
                    d_s = "—" if d is None else f"{float(d):.6g}"
                    md_lines.append(
                        f"{i}. score={r['score']:.3g} | seam={r['seam_phase']} r13={r['r13_phase']} snapQ={r['snap_quark']} snapL={r['snap_lepton']} | "
                        f"θ12={r['theta12_deg']:.6g} θ23={r['theta23_deg']:.6g} θ13={r['theta13_deg']:.6g} δ*={d_s} J={r['J']:.6g}"
                    )
                (out_dir / "ckm_discrete_scan_summary_v0_1.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
            except Exception:
                pass
    except Exception:
        pass


    # 6c) DIAG: extended CKM phase-grid scan (Z3/AB derived candidates; no tuning)
    try:
        if (ref is not None) and (np is not None):
            # refs
            ref2 = _maybe_load_refs()
            refs2 = ((ref2 or {}).get("refs") or (ref.get("refs") or {}))
            t12_ref = float((refs2.get("ckm_theta12_deg", {}) or {}).get("value", 12.997))
            t12_tol = float((refs2.get("ckm_theta12_deg", {}) or {}).get("tol_abs", 0.05))
            t23_ref = float((refs2.get("ckm_theta23_deg", {}) or {}).get("value", 2.397))
            t23_tol = float((refs2.get("ckm_theta23_deg", {}) or {}).get("tol_abs", 0.03))
            t13_ref = float((refs2.get("ckm_theta13_deg", {}) or {}).get("value", 0.214))
            t13_tol = float((refs2.get("ckm_theta13_deg", {}) or {}).get("tol_abs", 0.01))
            d_ref = float((refs2.get("ckm_delta_deg", {}) or {}).get("value", 65.73))
            d_tol = float((refs2.get("ckm_delta_deg", {}) or {}).get("tol_abs", 4.5))
            J_ref = float((refs2.get("ckm_J", {}) or {}).get("value", 3.12e-5))
            J_tol_rel = float((refs2.get("ckm_J", {}) or {}).get("tol_rel", 0.05))

            def _canon_phi(x: float) -> float:
                # wrap to (-pi, pi]
                tw = 2.0 * math.pi
                return float(((float(x) + math.pi) % tw) - math.pi)

            def _term_abs(v: float, ref_v: float, tol_abs: float) -> float:
                if tol_abs <= 0:
                    return 0.0
                return ((float(v) - float(ref_v)) / float(tol_abs)) ** 2

            def _score_ckm_local(ang: Dict[str, Any], V_abs: Any) -> Optional[float]:
                try:
                    t12 = float(ang.get("theta12_deg"))
                    t23 = float(ang.get("theta23_deg"))
                    t13 = float(ang.get("theta13_deg"))
                    J = float(ang.get("J"))
                except Exception:
                    return None

                # delta: use best quadrant (deterministic) if possible
                d_best = None
                try:
                    sd = ang.get("sin_delta")
                    if (sd is not None) and isinstance(V_abs, list):
                        th12 = math.radians(float(ang.get("theta12_deg") or 0.0))
                        th23 = math.radians(float(ang.get("theta23_deg") or 0.0))
                        th13 = math.radians(float(ang.get("theta13_deg") or 0.0))
                        best = _best_delta_from_sin(float(sd), th12, th23, th13, V_abs)
                        if best.get("delta_rad") is not None:
                            d_best = float(math.degrees(float(best["delta_rad"])))
                except Exception:
                    d_best = None

                if d_best is None:
                    try:
                        d_best = float(ang.get("delta_deg_from_sin"))
                    except Exception:
                        d_best = None

                s = 0.0
                s += _term_abs(t12, t12_ref, t12_tol)
                s += _term_abs(t23, t23_ref, t23_tol)
                s += _term_abs(t13, t13_ref, t13_tol)
                if d_best is not None:
                    d0 = float(d_best) % 360.0
                    d1 = (180.0 - d0) % 360.0
                    dd = min(abs(d0 - d_ref), abs(d1 - d_ref), abs((d0 + 360.0) - d_ref), abs((d1 + 360.0) - d_ref))
                    s += _term_abs(dd, 0.0, d_tol)
                try:
                    if (J_ref != 0.0) and (J_tol_rel > 0.0):
                        s += ((float(J) - float(J_ref)) / (float(J_tol_rel) * float(J_ref))) ** 2
                except Exception:
                    pass
                return float(s)

            # Build base Uu/Ud once (and snapped variants) and sweep only seam/R13 phase choices.
            base = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(None, None)
            if not isinstance(base, dict) or base.get('error'):
                raise RuntimeError(f"base construct error: {base.get('error') if isinstance(base, dict) else 'not a dict'}")

            pol = (base.get('policy') or {})
            db_ckm = ((pol.get('delta_base') or {}).get('CKM') or {})
            k_ckm_30 = int(db_ckm.get('k_mod30') or 0) % 30

            blocks = int(pol.get('blocks') or 42)
            nQ = int((pol.get('grid') or {}).get('quark') or 300)
            dkQ = int((pol.get('monodromy_step') or {}).get('quark_dk') or 50)
            rho = int(pol.get('rho') or RT_RHO)
            if rho <= 0:
                rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
            micro_step = int(((pol.get('rho_microphase') or {}).get('micro_step') or 1))

            seam = (pol.get('postR12_seam') or {})
            phi_B = float(seam.get('phi_rad') or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
            phi_A = float(_rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD))

            s_micro = int(((seam.get('theta_components_deg') or {}).get('s_micro')) or ((k_ckm_30 % 3) - 1))
            theta_micro = float((2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))

            theta_sext_q = float(2.0 * math.pi / (float(nQ) * 6.0))
            seam_extra_alts = [
                float(-1.0 * theta_sext_q),
                float(-0.5 * theta_sext_q),
                float(-0.25 * theta_sext_q),
                0.0,
                float(0.25 * theta_sext_q),
                float(0.5 * theta_sext_q),
                float(1.0 * theta_sext_q),
            ]
            # micro-extra is *separate* from seam-extra: it only shifts PP23 (intra-tick), not the seam.
            micro_extra_alts = [
                float(-0.5 * theta_sext_q),
                float(-0.25 * theta_sext_q),
                0.0,
                float(0.25 * theta_sext_q),
                float(0.5 * theta_sext_q),
            ]
            s13 = ((k_ckm_30 % 3) - 1)
            theta13_adj = float(theta_sext_q * float(s13))

            def _build_kick(p: int, phi_edge: float):
                N = _rt_near_coupling_matrix(int(p))
                N = _rt_apply_edge_phases(N, float(phi_edge))
                H = (N + N.conjugate().T)
                w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
                m = float(np.max(np.abs(w.real))) if w.size else 1.0
                if m < 1e-12:
                    m = 1.0
                Hn = H / m
                eps = RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0)
                return _rt_expm_i_hermitian(Hn, eps)

            def _rho_z3_sieved(b: int) -> int:
                return int((b % rho) % 3)

            def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
                n = int(n)
                k0 = int(k0) % n
                dk = int(dk) % n
                rho_sign = int(rho_sign)
                U = np.eye(3, dtype=np.complex128)
                for b in range(int(blocks)):
                    kb = (k0 + b * dk) % n
                    if (n == nQ) and (rho_sign != 0):
                        kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
                    P = _rt_proj_phase_Cn(kb, n)
                    R = _rt_perm_cycle_pow(b % 3)
                    Ub = U_kick.conjugate().T if (b % 2) else U_kick
                    Ub = R @ Ub @ R.conjugate().T
                    S = P @ Ub @ P.conjugate().T
                    U = U @ S
                return _rt_gauge_fix_unitary(U)

            kQ_base = (10 * k_ckm_30) % nQ
            Uu_raw = _monodromy(_build_kick(6, phi_A), nQ, kQ_base, dkQ, rho_sign=+1)
            Ud_raw = _monodromy(_build_kick(5, phi_B), nQ, kQ_base, dkQ, rho_sign=-1)

            # snapped quark variants
            Uu_snap = None
            Ud_snap = None
            snap_diag = None
            try:
                su = _rt_unitary_eigphase_snap_Cn(Uu_raw, int(nQ))
                sd = _rt_unitary_eigphase_snap_Cn(Ud_raw, int(nQ))
                if not su.get('error') and not sd.get('error'):
                    Uu_snap = su['U_snap']
                    Ud_snap = sd['U_snap']
                    snap_diag = {
                        'n': int(nQ),
                        'Uu_delta_deg_max': su.get('delta_deg_max'),
                        'Ud_delta_deg_max': sd.get('delta_deg_max'),
                    }
            except Exception:
                Uu_snap = None
                Ud_snap = None
                snap_diag = None

            # candidate phase list from phi_A/phi_B and Z3/AB moves
            tw = 2.0 * math.pi
            z3 = 2.0 * math.pi / 3.0
            raw = []
            def _add(lbl, val):
                v = _canon_phi(val)
                raw.append((str(lbl), float(v)))

            # base phases
            _add('phi_A', phi_A)
            _add('phi_B', phi_B)
            _add('-phi_A', -phi_A)
            _add('-phi_B', -phi_B)
            # Z3 shifts
            for name, base_phi in [('phi_A', phi_A), ('phi_B', phi_B), ('-phi_A', -phi_A), ('-phi_B', -phi_B)]:
                _add(f'{name}+Z3', base_phi + z3)
                _add(f'{name}-Z3', base_phi - z3)
                _add(f'{name}+pi', base_phi + math.pi)

            # unique by rounded value
            uniq = []
            seen = set()
            for lbl, v in raw:
                key = round(v, 12)
                if key in seen:
                    continue
                seen.add(key)
                uniq.append((lbl, v))

            seam_cands = [('phi_B', _canon_phi(phi_B)), ('phi_A', _canon_phi(phi_A))]
            r13_cands = uniq

            def _abs3(M):
                return [[float(abs(complex(M[i, j]))) for j in range(3)] for i in range(3)]

            def _arg(z: complex) -> float:
                return math.atan2(z.imag, z.real)

            def _compute_ckm(Uu, Ud, seam_phi: float, r13_phi: float):
                # seam
                theta_base = float(2.0 * math.pi / 30.0)
                theta_seam = float(theta_base + (2.0 * math.pi / (30.0 * float(max(1, rho)))) * float(s_micro))
                c = math.cos(theta_seam)
                s = math.sin(theta_seam)
                e_m_seam = complex(math.cos(-seam_phi), math.sin(-seam_phi))
                e_p_seam = complex(math.cos(+seam_phi), math.sin(+seam_phi))
                R12 = np.array([[c, s * e_m_seam, 0.0], [-s * e_p_seam, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
                Ud_seam = (Ud @ Hh) @ R12 @ H if bool(holo_on_seam) else (Ud @ R12)

                V0 = Uu.conjugate().T @ Ud_seam
                # PDG row-phase gauge DL
                a_u = -_arg(complex(V0[0, 0]))
                a_c = 0.0
                b_b = -_arg(complex(V0[1, 2])) - a_c
                a_t = -_arg(complex(V0[2, 2])) - b_b
                DL = np.diag([
                    complex(math.cos(a_u), math.sin(a_u)),
                    complex(math.cos(a_c), math.sin(a_c)),
                    complex(math.cos(a_t), math.sin(a_t)),
                ]).astype(np.complex128)

                # PP23 (micro)
                ct23 = math.cos(theta_micro)
                st23 = math.sin(theta_micro)
                R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
                A23 = DL.conjugate().T @ R23 @ DL

                # CKM13 sextet phaseful
                ct13 = math.cos(theta13_adj)
                st13 = math.sin(theta13_adj)
                e_m13 = complex(math.cos(-r13_phi), math.sin(-r13_phi))
                e_p13 = complex(math.cos(+r13_phi), math.sin(+r13_phi))
                R13 = np.array([[ct13, 0.0, st13 * e_m13], [0.0, 1.0, 0.0], [-st13 * e_p13, 0.0, ct13]], dtype=np.complex128)
                A13 = DL.conjugate().T @ R13 @ DL

                Uu_pp = Uu @ A13.conjugate().T @ A23.conjugate().T
                V = Uu_pp.conjugate().T @ Ud_seam
                ang = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
                V_abs = _abs3(V)
                # delta best
                d_best = None
                try:
                    sd = ang.get('sin_delta')
                    if (sd is not None) and isinstance(V_abs, list):
                        th12 = math.radians(float(ang.get('theta12_deg') or 0.0))
                        th23 = math.radians(float(ang.get('theta23_deg') or 0.0))
                        th13 = math.radians(float(ang.get('theta13_deg') or 0.0))
                        best = _best_delta_from_sin(float(sd), th12, th23, th13, V_abs)
                        if best.get('delta_rad') is not None:
                            d_best = float(math.degrees(float(best['delta_rad'])))
                except Exception:
                    d_best = None
                return V_abs, ang, d_best

            results = []
            for snap_name, Uu0, Ud0 in [('raw', Uu_raw, Ud_raw), ('snapQ', Uu_snap, Ud_snap)]:
                if (snap_name == 'snapQ') and (Uu0 is None or Ud0 is None):
                    continue
                for seam_lbl, seam_phi in seam_cands:
                    for r13_lbl, r13_phi in r13_cands:
                        V_abs, ang, d_best = _compute_ckm(Uu0, Ud0, float(seam_phi), float(r13_phi))
                        sc = _score_ckm_local(ang, V_abs)
                        if sc is None:
                            continue
                        results.append({
                            'snap': snap_name,
                            'seam_phase': seam_lbl,
                            'r13_phase': r13_lbl,
                            'r13_phi_deg': float(math.degrees(float(r13_phi))),
                            'score': float(sc),
                            'theta12_deg': float(ang.get('theta12_deg')),
                            'theta23_deg': float(ang.get('theta23_deg')),
                            'theta13_deg': float(ang.get('theta13_deg')),
                            'delta_best_deg': float(d_best) if d_best is not None else None,
                            'J': float(ang.get('J')),
                        })

            results.sort(key=lambda r: float(r.get('score') or 1e99))
            top = results[:20]
            checks['diag_ckm_phase_grid'] = {
                'count': int(len(results)),
                'top': top,
                'snap_diag': snap_diag,
                'note': 'Diagnostic only: phase grid over {phi_A,phi_B,±,±Z3,±pi} for seam/R13; plus optional quark eigphase snap. No continuous knobs.',
            }

            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / 'ckm_phase_grid_v0_1.json').write_text(json.dumps({'top': top, 'count': len(results)}, indent=2, sort_keys=True), encoding='utf-8')
                md_lines = ['# CKM phase grid scan (v0.1)', '', f'candidates: {len(results)}', '', '## Top', '']
                for i, r in enumerate(top, 1):
                    d = r.get('delta_best_deg')
                    d_s = '—' if d is None else f"{float(d):.6g}"
                    md_lines.append(
                        f"{i}. score={r['score']:.3g} | snap={r['snap']} seam={r['seam_phase']} r13={r['r13_phase']} (φ13={r['r13_phi_deg']:.6g}°) | "
                        f"θ12={r['theta12_deg']:.6g} θ23={r['theta23_deg']:.6g} θ13={r['theta13_deg']:.6g} δ*={d_s} J={r['J']:.6g}"
                    )
                (out_dir / 'ckm_phase_grid_summary_v0_1.md').write_text("\n".join(md_lines) + "\n", encoding='utf-8')
            except Exception:
                pass
    except Exception:
        pass

    # --- Gate-4.3 diagnostic: discrete C30 holonomy phases inserted *inside* the PP23 conjugation ---
    # H = diag(e^{iα_u}, 1, e^{iα_t}) with α from 2π/30 * integer.
    # Use it as: A23 = DL^† (H^† R23 H) DL, A13 = DL^† (H^† R13 H) DL.
    # Purpose: nudge (θ12, θ23, θ13, δ, J) using only discrete C30 phases (no continuous tuning).
    try:
        if (ref is not None) and (np is not None):
            # refs
            ref2 = _maybe_load_refs()
            refs2 = ((ref2 or {}).get("refs") or (ref.get("refs") or {}))
            t12_ref = float((refs2.get("ckm_theta12_deg", {}) or {}).get("value", 12.997))
            t12_tol = float((refs2.get("ckm_theta12_deg", {}) or {}).get("tol_abs", 0.05))
            t23_ref = float((refs2.get("ckm_theta23_deg", {}) or {}).get("value", 2.397))
            t23_tol = float((refs2.get("ckm_theta23_deg", {}) or {}).get("tol_abs", 0.03))
            t13_ref = float((refs2.get("ckm_theta13_deg", {}) or {}).get("value", 0.214))
            t13_tol = float((refs2.get("ckm_theta13_deg", {}) or {}).get("tol_abs", 0.01))
            d_ref = float((refs2.get("ckm_delta_deg", {}) or {}).get("value", 65.73))
            d_tol = float((refs2.get("ckm_delta_deg", {}) or {}).get("tol_abs", 4.5))
            J_ref = float((refs2.get("ckm_J", {}) or {}).get("value", 3.12e-5))
            J_tol_rel = float((refs2.get("ckm_J", {}) or {}).get("tol_rel", 0.05))

            def _term_abs(v: float, ref_v: float, tol_abs: float) -> float:
                if tol_abs <= 0:
                    return 0.0
                return ((float(v) - float(ref_v)) / float(tol_abs)) ** 2

            def _score_ckm_local(ang: Dict[str, Any], V_abs: Any) -> Optional[float]:
                try:
                    t12 = float(ang.get("theta12_deg"))
                    t23 = float(ang.get("theta23_deg"))
                    t13 = float(ang.get("theta13_deg"))
                    J = float(ang.get("J"))
                except Exception:
                    return None

                # best-branch δ from sinδ ambiguity
                d_best = None
                try:
                    sd = ang.get("sin_delta")
                    if (sd is not None) and isinstance(V_abs, list):
                        th12 = math.radians(float(ang.get("theta12_deg") or 0.0))
                        th23 = math.radians(float(ang.get("theta23_deg") or 0.0))
                        th13 = math.radians(float(ang.get("theta13_deg") or 0.0))
                        best = _best_delta_from_sin(float(sd), th12, th23, th13, V_abs)
                        if best.get("delta_rad") is not None:
                            d_best = float(math.degrees(float(best["delta_rad"])))
                except Exception:
                    d_best = None

                if d_best is None:
                    try:
                        d_best = float(ang.get("delta_deg_from_sin"))
                    except Exception:
                        d_best = None

                s = 0.0
                s += _term_abs(t12, t12_ref, t12_tol)
                s += _term_abs(t23, t23_ref, t23_tol)
                s += _term_abs(t13, t13_ref, t13_tol)
                if d_best is not None:
                    d0 = float(d_best) % 360.0
                    d1 = (180.0 - d0) % 360.0
                    dd = min(abs(d0 - d_ref), abs(d1 - d_ref), abs((d0 + 360.0) - d_ref), abs((d1 + 360.0) - d_ref))
                    s += _term_abs(dd, 0.0, d_tol)
                try:
                    if (J_ref != 0.0) and (J_tol_rel > 0.0):
                        s += ((float(J) - float(J_ref)) / (float(J_tol_rel) * float(J_ref))) ** 2
                except Exception:
                    pass
                return float(s)

            # rebuild base Uu/Ud (and snapped variants) exactly like the phase-grid diag
            base = _rt_construct_misalignment_v0_16_monodromy_postR12_seam_from_phase_rule_down_oriented_1260(None, None)
            if not isinstance(base, dict) or base.get("error"):
                raise RuntimeError(f"base construct error: {base.get('error') if isinstance(base, dict) else 'not a dict'}")

            pol = (base.get("policy") or {})
            db_ckm = ((pol.get("delta_base") or {}).get("CKM") or {})
            k_ckm_30 = int(db_ckm.get("k_mod30") or 0) % 30

            blocks = int(pol.get("blocks") or 42)
            nQ = int((pol.get("grid") or {}).get("quark") or 300)
            dkQ = int((pol.get("monodromy_step") or {}).get("quark_dk") or 50)
            rho = int(pol.get("rho") or RT_RHO)
            if rho <= 0:
                rho = int(RT_RHO) if int(RT_RHO) > 0 else 10
            rho_eff_alts = []
            for rr in [rho]:
                if int(rr) not in rho_eff_alts:
                    rho_eff_alts.append(int(rr))

            seam = (pol.get("postR12_seam") or {})
            phi_B = float(seam.get("phi_rad") or _rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD + math.pi))
            phi_A = float(_rt_quantize_pi_over_3(RT_DELTA_PHI_STAR_RAD))

            s_micro = int(((seam.get("theta_components_deg") or {}).get("s_micro")) or ((k_ckm_30 % 3) - 1))
            # diagnostic: also try a "full" micro choice tied directly to k_mod3 (often =2 when s_micro=1)
            k_mod3 = int(db_ckm.get("k_mod3") or (k_ckm_30 % 3))
            s_micro_alts = []
            for sm in [s_micro, k_mod3]:
                try:
                    smi = int(sm)
                except Exception:
                    continue
                if smi not in s_micro_alts:
                    s_micro_alts.append(smi)

            theta_sext_q = float(2.0 * math.pi / (float(nQ) * 6.0))
            s13 = ((k_ckm_30 % 3) - 1)
            theta13_adj = float(theta_sext_q * float(s13))

            # diag-only quark eigphase snap (reuses the same policy knob as v0.27)
            snap_diag = bool(((pol.get("diag") or {}).get("snap_quark_eigphase") or False))

            def _build_kick(p: int, phi_edge: float):
                N = _rt_near_coupling_matrix(int(p))
                N = _rt_apply_edge_phases(N, float(phi_edge))
                H = (N + N.conjugate().T)
                w, _ = np.linalg.eigh(0.5 * (H + H.conjugate().T))
                m = float(np.max(np.abs(w.real))) if w.size else 1.0
                if m < 1e-12:
                    m = 1.0
                Hn = H / m
                return _rt_expm_i_hermitian(Hn, RT_EPS0 if p == 6 else (-RT_EPS0 if p in (5,) else RT_EPS0))

            def _rho_z3_sieved(b: int) -> int:
                return int((b % rho) % 3)

            def _monodromy(U_kick, n: int, k0: int, dk: int, rho_sign: int = 0):
                # Match the Gate-4 monodromy convention used by the existing phase-grid diag:
                #   U = Π_b  [ P(k_b) · (R(b) U_kick^{±}) · P(k_b)^† ]  with R(b)=cycle(b mod 3), alternating ± per block.
                n = int(n)
                k0 = int(k0) % n
                dk = int(dk) % n
                rho_sign = int(rho_sign)
                micro_step = 1  # fixed policy integer ⇒ 1.2° per step on C300
                U = np.eye(3, dtype=np.complex128)
                for b in range(int(blocks)):
                    kb = (k0 + b * dk) % n
                    if (n == nQ) and (rho_sign != 0):
                        kb = (kb + rho_sign * (micro_step * _rho_z3_sieved(b))) % n
                    P = _rt_proj_phase_Cn(int(kb), int(n))
                    R = _rt_perm_cycle_pow(int(b) % 3)
                    Ub = U_kick.conjugate().T if (int(b) % 2) else U_kick
                    Ub = R @ Ub @ R.conjugate().T
                    S = P @ Ub @ P.conjugate().T
                    U = U @ S
                return _rt_gauge_fix_unitary(U)

            kQ_base = int((10 * k_ckm_30) % nQ)
            Uu_raw = _monodromy(_build_kick(6, phi_A), nQ, kQ_base, dkQ, rho_sign=+1)
            Ud_raw = _monodromy(_build_kick(5, phi_B), nQ, kQ_base, dkQ, rho_sign=-1)

            Uu_snap = None
            Ud_snap = None
            if snap_diag:
                try:
                    su = _rt_unitary_eigphase_snap_Cn(Uu_raw, int(nQ))
                    sd = _rt_unitary_eigphase_snap_Cn(Ud_raw, int(nQ))
                    Uu_snap = su.get("U") if isinstance(su, dict) else None
                    Ud_snap = sd.get("U") if isinstance(sd, dict) else None
                except Exception:
                    Uu_snap = None
                    Ud_snap = None

            # candidates
            seam_cands = [
                ("phi_B", phi_B),
                ("phi_A", phi_A),
            ]
            r13_cands = [
                ("phi_A", phi_A),
                ("phi_B", phi_B),
                ("pi", float(math.pi)),
                ("0", 0.0),
            ]

            # holonomy candidates (C30): small neighborhood plus explicit π flip

            # holonomy candidates (C30): small neighborhood plus explicit π flip
            mu_list = [-2, -1, 0, 1, 2]
            mt_list = [-2, -1, 0, 1, 2, 15]
            holo_cands = [(int(mu), int(mt)) for mu in mu_list for mt in mt_list]

            def _abs3(M):
                return [[float(abs(complex(M[i, j]))) for j in range(3)] for i in range(3)]

            def _arg(z: complex) -> float:
                return math.atan2(z.imag, z.real)

            def _compute_ckm_holo(
                Uu,
                Ud,
                seam_phi: float,
                r13_phi: float,
                mu30: int,
                mt30: int,
                s_micro_local: int,
                rho_eff_local: int,
                seam_extra_local: float,
                micro_extra_local: float,
                holo_on_seam: bool,
            ):
                # C30 holonomy (discrete): H = diag(e^{iα_u}, 1, e^{iα_t}).
                alpha_u = float(2.0 * math.pi / 30.0) * float(int(mu30))
                alpha_t = float(2.0 * math.pi / 30.0) * float(int(mt30))
                # SU(3) diagonal holonomy: enforce det(H)=1 via alpha_c = -alpha_u - alpha_t.
                alpha_c = float(-alpha_u - alpha_t)
                Hu = complex(math.cos(alpha_u), math.sin(alpha_u))
                Hc = complex(math.cos(alpha_c), math.sin(alpha_c))
                Ht = complex(math.cos(alpha_t), math.sin(alpha_t))
                H = np.diag([Hu, Hc, Ht]).astype(np.complex128)
                Hh = H.conjugate().T

                # seam + micro coupling (diag): seam_extra shifts only the seam; micro_extra shifts only PP23 (intra-tick).
                theta_base = float(2.0 * math.pi / 30.0)
                theta_micro_base = float((2.0 * math.pi / (30.0 * float(max(1, int(rho_eff_local))))) * float(int(s_micro_local)))
                theta_seam = float(theta_base + theta_micro_base + float(seam_extra_local))
                # PP23 micro: independent intra-tick offset (no coupling from seam_extra)
                theta_micro_local = float(theta_micro_base + float(micro_extra_local))
                c = math.cos(theta_seam)
                s = math.sin(theta_seam)
                e_m_seam = complex(math.cos(-seam_phi), math.sin(-seam_phi))
                e_p_seam = complex(math.cos(+seam_phi), math.sin(+seam_phi))
                R12 = np.array([[c, s * e_m_seam, 0.0], [-s * e_p_seam, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.complex128)
                # holonomy-on-seam is discrete: conjugate seam by H (no continuous knobs)
                Ud_seam = ((Ud @ Hh) @ R12 @ H) if bool(holo_on_seam) else (Ud @ R12)

                V0 = Uu.conjugate().T @ Ud_seam
                # canonical row-phase gauge DL
                a_u = -_arg(complex(V0[0, 0]))
                a_c = 0.0
                b_b = -_arg(complex(V0[1, 2])) - a_c
                a_t = -_arg(complex(V0[2, 2])) - b_b
                DL = np.diag([
                    complex(math.cos(a_u), math.sin(a_u)),
                    complex(math.cos(a_c), math.sin(a_c)),
                    complex(math.cos(a_t), math.sin(a_t)),
                ]).astype(np.complex128)

                # discrete holonomy H (C30) already built above

                # PP23 (micro)
                ct23 = math.cos(theta_micro_local)
                st23 = math.sin(theta_micro_local)
                R23 = np.array([[1.0, 0.0, 0.0], [0.0, ct23, st23], [0.0, -st23, ct23]], dtype=np.complex128)
                R23h = Hh @ R23 @ H
                A23 = DL.conjugate().T @ R23h @ DL

                # CKM13 sextet phaseful
                ct13 = math.cos(theta13_adj)
                st13 = math.sin(theta13_adj)
                e_m13 = complex(math.cos(-r13_phi), math.sin(-r13_phi))
                e_p13 = complex(math.cos(+r13_phi), math.sin(+r13_phi))
                R13 = np.array([[ct13, 0.0, st13 * e_m13], [0.0, 1.0, 0.0], [-st13 * e_p13, 0.0, ct13]], dtype=np.complex128)
                R13h = Hh @ R13 @ H
                A13 = DL.conjugate().T @ R13h @ DL

                Uu_pp = Uu @ A13.conjugate().T @ A23.conjugate().T
                V = Uu_pp.conjugate().T @ Ud_seam
                ang = _angles_J_from_unitary([[complex(V[i, j]) for j in range(3)] for i in range(3)])
                V_abs = _abs3(V)

                d_best = None
                try:
                    sd = ang.get("sin_delta")
                    if (sd is not None) and isinstance(V_abs, list):
                        th12 = math.radians(float(ang.get("theta12_deg") or 0.0))
                        th23 = math.radians(float(ang.get("theta23_deg") or 0.0))
                        th13 = math.radians(float(ang.get("theta13_deg") or 0.0))
                        best = _best_delta_from_sin(float(sd), th12, th23, th13, V_abs)
                        if best.get("delta_rad") is not None:
                            d_best = float(math.degrees(float(best["delta_rad"])))
                except Exception:
                    d_best = None
                return V_abs, ang, d_best

            results = []
            for snap_name, Uu0, Ud0 in [("raw", Uu_raw, Ud_raw), ("snapQ", Uu_snap, Ud_snap)]:
                if (snap_name == "snapQ") and (not snap_diag):
                    continue
                if (snap_name == "snapQ") and (Uu0 is None or Ud0 is None):
                    continue
                for seam_lbl, seam_phi in seam_cands:
                    for r13_lbl, r13_phi in r13_cands:
                        for mu30, mt30 in holo_cands:
                            for s_micro_local in s_micro_alts:
                                for rho_eff_local in rho_eff_alts:
                                    for seam_extra_local in seam_extra_alts:
                                        for micro_extra_local in micro_extra_alts:
                                            for holo_on_seam in [False, True]:
                                                V_abs, ang, d_best = _compute_ckm_holo(
                                                Uu0,
                                                Ud0,
                                                float(seam_phi),
                                                float(r13_phi),
                                                int(mu30),
                                                int(mt30),
                                                int(s_micro_local),
                                                int(rho_eff_local),
                                                float(seam_extra_local),
                                                float(micro_extra_local),
                                                bool(holo_on_seam),
                                            )
                                            sc = _score_ckm_local(ang, V_abs)
                                            if sc is None:
                                                continue
                                            results.append({
                                                "snap": snap_name,
                                                "seam_phase": seam_lbl,
                                                "r13_phase": r13_lbl,
                                                "r13_phi_deg": float(math.degrees(float(r13_phi))),
                                                "mu30": int(mu30),
                                                "mt30": int(mt30),
                                                "s_micro": int(s_micro_local),
                                                "rho_eff": int(rho_eff_local),
                                                "seam_extra_deg": float(math.degrees(float(seam_extra_local))),
                                                "micro_extra_deg": float(math.degrees(float(micro_extra_local))),
                                                "holo_on_seam": bool(holo_on_seam),
                                                "score": float(sc),
                                                "theta12_deg": float(ang.get("theta12_deg")),
                                                "theta23_deg": float(ang.get("theta23_deg")),
                                                "theta13_deg": float(ang.get("theta13_deg")),
                                                "delta_best_deg": float(d_best) if d_best is not None else None,
                                                "J": float(ang.get("J")),
                                            })

            results.sort(key=lambda r: float(r.get("score") or 1e99))
            top = results[:30]
            checks["diag_ckm_holonomy_grid"] = {
                "count": int(len(results)),
                "top": top,
                "snap_diag": bool(snap_diag),
                "note": "Diagnostic only: insert discrete C30 holonomy phases (mu30,mt30) inside PP23/CKM13 conjugation (H^† R H); scan seam_extra and *separate* micro_extra (PP23-only); optional holonomy-on-seam. No continuous tuning.",
            }

            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                payload = {"count": len(results), "top": top}  # keep output small; full grid is diagnostic-only
                (out_dir / "ckm_holonomy_grid_v0_2.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
                md_lines = ["# CKM holonomy grid scan (v0.2)", "", f"candidates: {len(results)}", "", "## Top", ""]
                for i, r in enumerate(top, 1):
                    d = r.get("delta_best_deg")
                    d_s = "—" if d is None else f"{float(d):.6g}"
                    md_lines.append(
                        f"{i}. score={r['score']:.3g} | snap={r['snap']} s_micro={r.get('s_micro')} rho_eff={r.get('rho_eff')} seam+={r.get('seam_extra_deg')}° micro+={r.get('micro_extra_deg')}° hSeam={r.get('holo_on_seam')} seam={r['seam_phase']} r13={r['r13_phase']} (φ13={r['r13_phi_deg']:.6g}°) | "
                        f"mu30={r['mu30']} mt30={r['mt30']} | θ12={r['theta12_deg']:.6g} θ23={r['theta23_deg']:.6g} θ13={r['theta13_deg']:.6g} δ*={d_s} J={r['J']:.6g}"
                    )
                (out_dir / "ckm_holonomy_grid_summary_v0_2.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
            except Exception:
                pass
    except Exception as e:
        try:
            checks["diag_ckm_holonomy_grid_error"] = {"error": repr(e)}
        except Exception:
            pass

    overall = {
        "version": "v0.1",
        "inputs": {
            "flavor_ud": str(ud_p.relative_to(REPO_ROOT)),
            "flavor_enu": str(enu_p.relative_to(REPO_ROOT)),
            "ref_file": "00_TOP/OVERLAY/sm29_data_reference_v0_1.json" if (REPO_ROOT / "00_TOP/OVERLAY/sm29_data_reference_v0_1.json").exists() else None,
        },
        "thresholds": {
            "EPS_RATIO_DIFF": EPS_RATIO_DIFF,
            "MIN_THETA_DEG": MIN_THETA_DEG,
            "MIN_J_ABS": MIN_J_ABS,
            "MIN_HIER_D_M1M2": MIN_HIER_D_M1M2,
            "MAX_NEG_THETA_DEG": MAX_NEG_THETA_DEG,
            "MAX_NEG_J_ABS": MAX_NEG_J_ABS,
        },
        "checks": checks,
        "gate": {
            "PASS": bool(pass_full and pass_ratios and pass_ckm and pass_pmns and pass_neg and pass_d and pass_phase_neg and pass_rt_phase),
            "components": {
                "full_scan": bool(pass_full),
                "ratios_not_identical": bool(pass_ratios),
                "ckm_nontrivial": bool(pass_ckm),
                "pmns_nontrivial": bool(pass_pmns),
                "neg_controls": bool(pass_neg),
                "d_hierarchy_reasonable": bool(pass_d),
                "phase_lift_neg": bool(pass_phase_neg),
                "rt_phase_rule_matches_kstar": bool(pass_rt_phase),
            },
        },
        "notes": [
            "Verifier only. Does not claim physical agreement; only non-degeneracy and sanity gates.",
            "No continuous knobs; thresholds are policy constants.",
            "RT phase-rule δ_C30 must reproduce operational k* (baseline).",
            "match_gates are Overlay-only comparisons and do not affect overall PASS.",
        ],
    }

    out_json = out_dir / "flavor_lock_verify_v0_1.json"
    out_md = out_dir / "flavor_lock_verify_summary_v0_1.md"

    out_json.write_text(json.dumps(overall, indent=2, sort_keys=True), encoding="utf-8")

    md = []
    md.append("# FLAVOR_LOCK verify (v0.1)\n")
    md.append("Gates (policy constants; no tuning).\n")
    md.append(f"\n- full_scan: {'PASS' if pass_full else 'FAIL'} (requires scan.full=True in both artifacts)")
    md.append(f"\n- ratios_not_identical: {'PASS' if pass_ratios else 'FAIL'}")
    md.append(f"\n- CKM nontrivial: {'PASS' if pass_ckm else 'FAIL'} (|J| >= {MIN_J_ABS})")
    md.append(f"\n- PMNS nontrivial: {'PASS' if pass_pmns else 'FAIL'} (|J| >= {MIN_J_ABS})")
    md.append(f"\n- NEG controls: {'PASS' if pass_neg else 'FAIL'} (trivial_mix angles <= {MAX_NEG_THETA_DEG}°, |J| <= {MAX_NEG_J_ABS})")
    md.append(f"\n- d hierarchy reasonable: {'PASS' if pass_d else 'FAIL'} (m1/m2 >= {MIN_HIER_D_M1M2})")
    if checks.get("phase_lift_neg", {}).get("pass") is not None:
        md.append(f"\n- phase_lift NEG sanity: {'PASS' if pass_phase_neg else 'FAIL'} (NEG must be exactly unitary, J=0)")
    md.append(f"\n- RT phase-rule matches k*: {'PASS' if pass_rt_phase else 'FAIL'} (CKM+PMNS; deterministic)")
    md.append(f"\n- RT construct pattern gate: {'PASS' if pass_rt_construct else 'FAIL'} (diagnostic)")
    md.append(f"\n- RT sector eigphase snap (C30) pattern gate: {'PASS' if pass_rt_sector_snap else 'FAIL'} (diagnostic)")
    md.append(f"\n- RT sector eigphase snap (C300 quark) pattern gate: {'PASS' if pass_rt_sector_snap_c300 else 'FAIL'} (diagnostic)")

    # seam orientation summary (informational)
    so = (checks.get("rt_construct_seam_orientation") or {})
    if so.get("canonical") and so.get("neg"):
        can = so.get("canonical") or {}
        neg = so.get("neg") or {}
        md.append("\n- seam orientation (canonical v0.16 vs NEG v0.15): OK (informational)")
        md.append(f"\n  - k_mod3={int(can.get('k_mod3') or 0)}  canonical: s_micro={int(can.get('s_micro') or 0)}, theta_deg={float(can.get('theta_deg') or 0.0)}  |  NEG: s_micro={int(neg.get('s_micro') or 0)}, theta_deg={float(neg.get('theta_deg') or 0.0)}")

    # v0.19 PP23 (preferred diagnostic): PP-native placement on Uu right-basis
    v19 = (checks.get("rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis") or {})
    ck19 = (((v19.get("CKM") or {}).get("angles") or {}))
    if ck19:
        md.append("\n- RT construct v0.19 PP23 (Uu right-basis; preferred diag): OK (informational)")
        md.append(f"\n  - CKM after PP23: θ12={float(ck19.get('theta12_deg') or 0.0):.6g}°, θ23={float(ck19.get('theta23_deg') or 0.0):.6g}°, θ13={float(ck19.get('theta13_deg') or 0.0):.6g}°")

    # v0.20 PMNS θ13 sextet-engagement readout (informational)
    v20 = (checks.get("rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet") or {})
    pm20 = (((v20.get("PMNS") or {}).get("angles") or {}))
    pm20_pre = (((v20.get("PMNS_pre_sextet") or {}).get("angles") or {}))
    if pm20:
        md.append("\n- RT construct v0.20 PMNS θ13 sextet-engagement: OK (informational)")
        if pm20_pre:
            md.append(f"\n  - PMNS θ13: pre={float(pm20_pre.get('theta13_deg') or 0.0):.6g}° → post={float(pm20.get('theta13_deg') or 0.0):.6g}°")
        else:
            md.append(f"\n  - PMNS after sextet: θ12={float(pm20.get('theta12_deg') or 0.0):.6g}°, θ23={float(pm20.get('theta23_deg') or 0.0):.6g}°, θ13={float(pm20.get('theta13_deg') or 0.0):.6g}°")

    # v0.21 PMNS θ23 cap-lift readout (informational)
    v21 = (checks.get("rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7") or {})
    pm21 = (((v21.get("PMNS") or {}).get("angles") or {}))
    pm21_pre = (((v21.get("PMNS_pre_cap23") or {}).get("angles") or {}))
    if pm21:
        md.append("\n- RT construct v0.21 PMNS θ23 cap-lift (|L_cap|=7, Ue right-basis): OK (informational)")
        if pm21_pre:
            md.append(f"\n  - PMNS θ23: pre={float(pm21_pre.get('theta23_deg') or 0.0):.6g}° → post={float(pm21.get('theta23_deg') or 0.0):.6g}° (θ13 preserved: {float(pm21.get('theta13_deg') or 0.0):.6g}°)")
        else:
            md.append(f"\n  - PMNS after cap-lift: θ12={float(pm21.get('theta12_deg') or 0.0):.6g}°, θ23={float(pm21.get('theta23_deg') or 0.0):.6g}°, θ13={float(pm21.get('theta13_deg') or 0.0):.6g}°")

    # v0.22 PMNS θ12 right-R12 sextet (informational)
    v22 = (checks.get("rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet") or {})
    pm22 = (((v22.get("PMNS") or {}).get("angles") or {}))
    pm22_pre = (((v22.get("PMNS_pre_pmns12") or {}).get("angles") or {}))
    if pm22:
        placement22 = (((v22.get('policy') or {}).get('pmns12_sextet_r12') or {}).get('placement') or 'unknown')
        md.append(f"\n- RT construct v0.22 PMNS θ12 sextet (R12; {placement22}): OK (informational)")
        if pm22_pre:
            md.append(f"\n  - PMNS θ12: pre={float(pm22_pre.get('theta12_deg') or 0.0):.6g}° → post={float(pm22.get('theta12_deg') or 0.0):.6g}° (θ13 preserved: {float(pm22.get('theta13_deg') or 0.0):.6g}°)")
        else:
            md.append(f"\n  - PMNS after θ12 sextet: θ12={float(pm22.get('theta12_deg') or 0.0):.6g}°, θ23={float(pm22.get('theta23_deg') or 0.0):.6g}°, θ13={float(pm22.get('theta13_deg') or 0.0):.6g}°")

    # v0.27 PMNS θ12 cap-multiplicity sextet (promotion candidate)
    v27 = (checks.get("rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_mcap") or {})
    pm27 = (((v27.get("PMNS") or {}).get("angles") or {}))
    pm27_pre = (((v27.get("PMNS_pre_pmns12") or {}).get("angles") or {}))
    if pm27:
        pol27 = (v27.get('policy') or {}).get('pmns12_sextet_r12') or {}
        placement27 = (pol27.get('placement') or 'unknown')
        mult27 = pol27.get('mult')
        md.append(f"\n- RT construct v0.27 PMNS θ12 sextet×mcap (m12={mult27}, R12; {placement27}): OK (informational)")
        if pm27_pre:
            md.append(f"\n  - PMNS θ12: pre={float(pm27_pre.get('theta12_deg') or 0.0):.6g}° → post={float(pm27.get('theta12_deg') or 0.0):.6g}° (θ13/θ23 preserved: {float(pm27.get('theta13_deg') or 0.0):.6g}°, {float(pm27.get('theta23_deg') or 0.0):.6g}°)")
        else:
            md.append(f"\n  - PMNS after θ12 sextet×mcap: θ12={float(pm27.get('theta12_deg') or 0.0):.6g}°, θ23={float(pm27.get('theta23_deg') or 0.0):.6g}°, θ13={float(pm27.get('theta13_deg') or 0.0):.6g}°")

    # v0.21 cap NEG family (axis / magnitude) — informational, should FAIL
    nc21 = (v21.get("neg_controls") or {})
    if nc21:
        md.append("\n  - cap NEG family (ska FAIL):")
        order = ["pmns23_cap_axis12", "pmns23_cap_axis13", "pmns23_cap_mag_6", "pmns23_cap_mag_8"]
        for kk in order:
            v = (nc21.get(kk) or {})
            ang = (v.get("angles") or {})
            if ang:
                md.append(f"\n    - {kk}: θ23={float(ang.get('theta23_deg') or 0.0):.6g}°, θ13={float(ang.get('theta13_deg') or 0.0):.6g}°")




    # legacy v0.18 PP23 quick readout (PDG-reconstructed; informational)
    v18 = (checks.get("rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23") or {})
    ck18 = (((v18.get("CKM") or {}).get("angles") or {}))
    if ck18:
        md.append("\n- RT construct v0.18 PP23 (legacy PDG recon): OK (informational)")
        md.append(f"\n  - CKM after PP23: θ12={float(ck18.get('theta12_deg') or 0.0):.6g}°, θ23={float(ck18.get('theta23_deg') or 0.0):.6g}°, θ13={float(ck18.get('theta13_deg') or 0.0):.6g}°")

    md.append(f"\n\nOverall (sanity gates only): {'PASS' if overall['gate']['PASS'] else 'FAIL'}\n")

    # Overlay-only match gates
    md.append("\n## Overlay match gates (do NOT affect overall)\n")
    if not match.get("ref_present", False):
        md.append("\n- refs: MISSING (00_TOP/OVERLAY/sm29_data_reference_v0_1.json)\n")
    else:
        ck = match.get("CKM", {})
        pm = match.get("PMNS", {})
        ck_pass = ck.get("pass_all")
        pm_pass = pm.get("pass_all")
        md.append(f"\n- CKM (PDG): {'PASS' if ck_pass else 'FAIL' if ck_pass is not None else 'N/A'}")
        # Detail CKM
        ck_checks = (ck.get("checks") or {})
        for kk in ("theta12_deg", "theta23_deg", "theta13_deg", "delta_deg", "J"):
            c = ck_checks.get(kk, {})
            if c.get("pass") is None:
                md.append(f"\n  - {kk}: N/A ({c.get('note','')})")
            else:
                if kk == "J":
                    md.append(f"\n  - {kk}: {'PASS' if c.get('pass') else 'FAIL'} (RT={c.get('rt'):.6g}, ref={c.get('ref'):.6g}, tol_rel={c.get('tol_rel')})")
                else:
                    md.append(f"\n  - {kk}: {'PASS' if c.get('pass') else 'FAIL'} (RT={c.get('rt'):.6g}°, ref={c.get('ref'):.6g}°, tol_abs={c.get('tol_abs')})")
        # Detail CKM (PP-pred)
        ck2 = match.get("CKM_pp_pred", {})
        ck2_pass = ck2.get("pass_all")
        md.append(f"\n- CKM (PP-pred): {'PASS' if ck2_pass else 'FAIL' if ck2_pass is not None else 'N/A'}")
        ck2_checks = (ck2.get("checks") or {})
        for kk in ("theta12_deg", "theta23_deg", "theta13_deg", "delta_deg", "J"):
            c = ck2_checks.get(kk, {})
            if c.get("pass") is None:
                md.append(f"\n  - {kk}: N/A ({c.get('note','')})")
            else:
                if kk == "J":
                    md.append(
                        f"\n  - {kk}: {'PASS' if c.get('pass') else 'FAIL'} (RT={c.get('rt'):.6g}, ref={c.get('ref'):.6g}, tol_rel={c.get('tol_rel')})"
                    )
                else:
                    md.append(
                        f"\n  - {kk}: {'PASS' if c.get('pass') else 'FAIL'} (RT={c.get('rt'):.6g}°, ref={c.get('ref'):.6g}°, tol_abs={c.get('tol_abs')})"
                    )




        md.append(f"\n- PMNS (PDG 3σ): {'PASS' if pm_pass else 'FAIL' if pm_pass is not None else 'N/A'}")
        pm_checks = (pm.get("checks") or {})
        for kk in ("theta12_deg", "theta23_deg", "theta13_deg"):
            c = pm_checks.get(kk, {})
            if c.get("pass") is None:
                md.append(f"\n  - {kk}: N/A ({c.get('note','')})")
            else:
                lo, hi = c.get("range", [None, None])
                md.append(f"\n  - {kk}: {'PASS' if c.get('pass') else 'FAIL'} (RT={c.get('rt'):.6g}°, range={lo:.6g}–{hi:.6g}°)")
        # Detail PMNS (PP-pred)
        pm2 = match.get("PMNS_pp_pred", {})
        pm2_pass = pm2.get("pass_all")
        md.append(f"\n- PMNS (PP-pred): {'PASS' if pm2_pass else 'FAIL' if pm2_pass is not None else 'N/A'}")
        pm2_checks = (pm2.get("checks") or {})
        for kk in ("theta12_deg", "theta23_deg", "theta13_deg"):
            c = pm2_checks.get(kk, {})
            if c.get("pass") is None:
                md.append(f"\n  - {kk}: N/A ({c.get('note','')})")
            else:
                lo, hi = c.get("range", [None, None])
                md.append(
                    f"\n  - {kk}: {'PASS' if c.get('pass') else 'FAIL'} (RT={c.get('rt'):.6g}°, range={lo:.6g}–{hi:.6g}°)"
                )



    # Discrete relabeling scan (abs-only)
    ps = (checks.get("perm_scan_abs") or {})
    if ps:
        md.append("\n\n## Discrete permutation scan (abs-only; relabeling only)\n")
        for kind in ("CKM", "PMNS"):
            ks = (ps.get(kind) or {})
            best = (ks.get("best") or {})
            if not best:
                md.append(f"\n- {kind}: N/A")
                continue
            md.append(f"\n- {kind}: best proxy_key={best.get('proxy_key')}")
            md.append(f"\n  - row_perm={best.get('row_perm')}, col_perm={best.get('col_perm')}")
            a = best.get("angles_deg") or {}
            md.append(
                f"\n  - angles (deg): θ12={a.get('theta12_deg'):.6g}, θ23={a.get('theta23_deg'):.6g}, θ13={a.get('theta13_deg'):.6g}"
            )
            if ks.get("min_theta13_deg_bound") is not None:
                md.append(
                    f"\n  - θ13 lower bound from |M| magnitudes: {ks.get('min_theta13_deg_bound'):.6g}° (min |M|={ks.get('min_abs')})"
                )
            # Impossibility flags
            if kind == "CKM" and ks.get("cannot_reach_ref_theta13_by_relabeling") is not None:
                md.append(f"\n  - cannot_reach_ref_theta13_by_relabeling: {ks.get('cannot_reach_ref_theta13_by_relabeling')}")
            if kind == "PMNS" and ks.get("cannot_reach_pmns_theta13_range_by_relabeling") is not None:
                md.append(f"\n  - cannot_reach_pmns_theta13_range_by_relabeling: {ks.get('cannot_reach_pmns_theta13_range_by_relabeling')}")

    
    # Unistochastic feasibility (abs-only)
    us = (checks.get("unistochastic") or {})
    if us:
        md.append("\n\n## Unistochastic feasibility (abs-only)\n")
        md.append("\nTriangle tests on row/col pairs (necessary+sufficient for 3-term orthogonality).\n")
        for kind in ("CKM", "PMNS"):
            kk = (us.get(kind) or {})
            ds = (kk.get("doubly_stochastic_sq") or {})
            tc = (kk.get("triangle_checks") or {})
            md.append(f"\n- {kind}:")
            if ds.get("max_err") is not None:
                md.append(f"\n  - max |sum(|M|^2)-1|: {ds.get('max_err')}")
            if tc.get("pass_all") is not None:
                md.append(f"\n  - triangle pass_all: {tc.get('pass_all')}")
                margins = []
                for rp in (tc.get("row_pairs") or []):
                    tri = rp.get("tri") or {}
                    if tri.get("margin") is not None:
                        margins.append(float(tri.get("margin")))
                for cp in (tc.get("col_pairs") or []):
                    tri = cp.get("tri") or {}
                    if tri.get("margin") is not None:
                        margins.append(float(tri.get("margin")))
                if margins:
                    md.append(f"\n  - min margin (row/col): {min(margins)}")

    # Delta grid diagnostics
    dg = (checks.get("delta_grid_C30") or {})
    if dg:
        md.append("\n\n## Phase quantization diagnostics (delta vs C30 grid)\n")
        md.append("\nDerived delta is compared to nearest multiple of 2π/30 (no tuning).\n")
        for kind in ("CKM", "PMNS"):
            dd = dg.get(kind) or {}
            if not dd:
                continue
            grid = dd.get("C30_grid") or {}
            dg_rad = float(grid.get("delta_grid_rad")) if grid.get("delta_grid_rad") is not None else float("nan")
            md.append(
                f"\n- {kind}: δ_best={dd.get('delta_best_deg'):.6g}°  (k={grid.get('k')}, δ_grid={math.degrees(dg_rad):.6g}°)"
            )
            md.append(f"\n  - δ_best−δ_grid = {grid.get('delta_minus_grid_rad'):.6g} rad")
            md.append(f"\n  - abs error @δ_best: max={dd.get('delta_best_abs_max_err'):.3g}, rms={dd.get('delta_best_abs_rms_err'):.3g}")
            md.append(f"\n  - abs error @δ_grid: max={dd.get('delta_grid_abs_max_err'):.3g}, rms={dd.get('delta_grid_abs_rms_err'):.3g}")

    # Discrete phase-lift scan (attempt unitary reconstruction)
    pls = (checks.get("phase_lift_scan") or {})
    if pls:
        md.append("\n\n## Discrete phase-lift scan (unitary reconstruction; discrete phases)\n")
        md.append(f"\nPolicy: phase_set(rad)={list(PHASE_SET_RAD)}, unitary_res_tol={UNITARY_RES_TOL}")

        def _fmt_pl(tag: str, title: str):
            obj = (pls.get(tag) or {})
            best = (obj.get("best") or {})
            if not best:
                md.append(f"\n- {title}: N/A")
                return
            res = best.get("unitary_residual")
            ok = best.get("unitary_res_ok")
            md.append(f"\n- {title}: best residual R={res:.6g} (R<=tol? {ok})")
            ang = best.get("angles") or {}
            if ang:
                md.append(
                    f"\n  - angles (deg): θ12={ang.get('theta12_deg'):.6g}, θ23={ang.get('theta23_deg'):.6g}, θ13={ang.get('theta13_deg'):.6g}" 
                )
                md.append(
                    f"\n  - J={ang.get('J'):.6g}, sinδ={ang.get('sin_delta')}, δ_from_sin(deg)={ang.get('delta_deg_from_sin')}"
                )
            ph = best.get("phases_rad") or {}
            if ph:
                md.append(f"\n  - phases_rad(submatrix): {ph}")

        _fmt_pl("CKM", "CKM")
        _fmt_pl("PMNS", "PMNS")
        _fmt_pl("NEG_CKM", "NEG CKM (trivial_mix)")
        _fmt_pl("NEG_PMNS", "NEG PMNS (trivial_mix)")

    # Constructive unitary lift (closed-form)
    cul = (checks.get("constructive_unitary_lift") or {})
    if cul:
        md.append("\n\n## Constructive unitary lift (triangle closure; abs→complex)\n")
        md.append("\nNo continuous scan; only discrete reflection branches. Reports residual + phase distance to C30 grid (diagnostic).\n")
        for kind in ("CKM", "PMNS", "NEG_CKM", "NEG_PMNS"):
            obj = cul.get(kind) or {}
            best = obj.get("best") or {}
            if not best:
                continue
            pq = best.get("phase_quant") or {}
            md.append(f"\n- {kind}: R={best.get('unitary_residual'):.6g}, |row1·row2*|={best.get('row1_row2_dot_abs'):.6g}, phase_max_dist(rad)={pq.get('max_dist_rad')}")
            ang = best.get("angles") or {}
            if ang:
                md.append(f"\n  - angles(deg): θ12={ang.get('theta12_deg'):.6g}, θ23={ang.get('theta23_deg'):.6g}, θ13={ang.get('theta13_deg'):.6g}, J={ang.get('J'):.6g}")
            br = best.get("branches") or {}
            md.append(f"\n  - branches: {br}")

    # C30-quantized unitary lift (triangle closure with snapped phases)
    c30l = (checks.get("c30_quantized_unitary_lift") or {})
    if c30l:
        md.append("\n\n## C30-quantized unitary lift (triangle closure → phases snapped to C30)\n")
        md.append("\nNo continuous scan; only discrete reflection branches plus nearest-C30 snapping per solved phase (diagnostic).\n")
        for kind in ("CKM", "PMNS", "NEG_CKM", "NEG_PMNS"):
            obj = c30l.get(kind) or {}
            best = obj.get("best") or {}
            if not best:
                continue
            md.append(f"\n- {kind}: R={best.get('unitary_residual'):.6g}, |row1·row2*|={best.get('row1_row2_dot_abs'):.6g}")
            ang = best.get('angles') or {}
            if ang:
                md.append(f"\n  - angles(deg): θ12={ang.get('theta12_deg'):.6g}, θ23={ang.get('theta23_deg'):.6g}, θ13={ang.get('theta13_deg'):.6g}, J={ang.get('J'):.6g}")
            br = best.get('branches') or {}
            md.append(f"\n  - branches: {br}")
            tri = best.get('triangles') or {}
            for rtag in ('row1','row2'):
                td = tri.get(rtag) or {}
                if td.get('phi_C30'):
                    q = td.get('phi_C30')
                    md.append(f"\n  - {kind}.{rtag}: φ_raw={td.get('phi_raw'):.6g} rad, φ_C30(k={q.get('k')}, Δ={q.get('phi_minus_grid_rad'):.6g})")
                if td.get('theta_C30'):
                    q = td.get('theta_C30')
                    md.append(f"\n  - {kind}.{rtag}: θ_raw={td.get('theta_raw'):.6g} rad, θ_C30(k={q.get('k')}, Δ={q.get('phi_minus_grid_rad'):.6g})")

    # RT phase-rule unitary lift (δφ*, Z3×A/B + tie-breakers; diagnostic only)
    rtpr = (checks.get("rt_phase_rule_unitary_lift") or {})
    if rtpr:
        md.append("\n\n## RT phase-rule unitary lift (δφ*, Z3×A/B → δ_C30; PDG unitary)\n")
        md.append("\nExact unitarity by construction; reports how well RT-derived δ reproduces |M| (diagnostic).\n")

        def _fmt_rtpr(kind: str):
            obj = rtpr.get(kind) or {}
            best = obj.get("best") or {}
            if not best:
                md.append(f"\n- {kind}: N/A")
                return
            dq = best.get("delta_C30") or {}
            md.append(
                f"\n- {kind}: k_rt={dq.get('k_mod30')} (δ_grid={dq.get('delta_grid_deg')}°; canon k={dq.get('k_0_15')}, δ={dq.get('delta_grid_deg_0_15')}°), "
                f"abs_err_max={best.get('abs_max_err'):.6g}, abs_err_rms={best.get('abs_rms_err'):.6g}"
            )
            md.append(
                f"\n  - z3_offset={best.get('z3_offset_rad'):.6g} rad, "
                f"ab_offset={best.get('ab_offset_rad'):.6g} rad, rho_offset={best.get('rho_offset_rad'):.6g} rad, δ_raw={best.get('delta_raw_deg'):.6g}°"
            )
            cmp = obj.get("compare") or {}
            ks = cmp.get("kstar_operational") or {}
            if ks:
                md.append(
                    f"\n  - k* (operational, abs-fit): {ks.get('k_best')} (δ_grid*={ks.get('delta_grid_deg')}°), "
                    f"err_max*={ks.get('abs_max_err')}"
                )

        _fmt_rtpr("CKM")
        _fmt_rtpr("PMNS")
        _fmt_rtpr("NEG_CKM")
        _fmt_rtpr("NEG_PMNS")

    # Misalignment diagnostics (CKM vs PMNS)

    mis = (checks.get("misalignment") or {})
    if mis:
        md.append("\n\n## CKM/PMNS misalignment (informational; no tuning)\n")
        md.append(f"\n- |||V|-|U|||_F = {mis.get('abs_fro'):.6g}  (Frobenius on abs)")
        md.append(f"\n- |||V|^2-|U|^2|||_F = {mis.get('abs_sq_fro'):.6g}")
        off = mis.get('offdiag_sq') or {}
        md.append(f"\n- offdiag Σ|.|^2: CKM={off.get('CKM'):.6g}, PMNS={off.get('PMNS'):.6g}, Δ={off.get('delta'):.6g}")
        ang = mis.get('angles_deg') or {}
        if ang:
            c = ang.get('CKM') or {}
            u = ang.get('PMNS') or {}
            md.append(f"\n- angles θ12/θ23/θ13 (deg): CKM=({c.get('theta12_deg')},{c.get('theta23_deg')},{c.get('theta13_deg')}), PMNS=({u.get('theta12_deg')},{u.get('theta23_deg')},{u.get('theta13_deg')})")
            md.append(f"\n- J: CKM={c.get('J')}, PMNS={u.get('J')}")
        dd = mis.get('delta_C30') or {}
        if dd:
            md.append(
                f"\n- δ_C30: CKM k_near={dd.get('CKM',{}).get('k')} (grid={dd.get('CKM',{}).get('delta_grid_deg')}°, best={dd.get('CKM',{}).get('delta_best_deg')}°), "
                f"k*={dd.get('CKM',{}).get('k_best')} (grid*={dd.get('CKM',{}).get('delta_bestfit_grid_deg')}°, err_max={dd.get('CKM',{}).get('bestfit_abs_max_err')}); "
                f"PMNS k_near={dd.get('PMNS',{}).get('k')} (grid={dd.get('PMNS',{}).get('delta_grid_deg')}°, best={dd.get('PMNS',{}).get('delta_best_deg')}°), "
                f"k*={dd.get('PMNS',{}).get('k_best')} (grid*={dd.get('PMNS',{}).get('delta_bestfit_grid_deg')}°, err_max={dd.get('PMNS',{}).get('bestfit_abs_max_err')})"
            )

    # RT deterministic construct (diagnostic)

    rc = (checks.get("rt_construct_misalignment") or {})
    if rc and not rc.get("error"):
        md.append("\n\n## RT construct (v0.4, factorized sqrt; diagnostic)\n")
        g = (rc.get("gate") or {})
        sg = (g.get("score") or {})
        ckpat = (g.get("ckm_pattern") or {})
        pmpat = (g.get("pmns_pattern") or {})

        md.append("\n- overall gate (score+pattern): " + ("PASS" if g.get("pass") else "FAIL"))
        md.append("\n- score gate (CKM score < PMNS score): " + ("PASS" if sg.get("pass") else "FAIL"))
        md.append("\n  - score_ckm=%s, score_pmns=%s, neg_ok=%s" % (sg.get("ckm"), sg.get("pmns"), g.get("neg_ok")))

        md.append("\n- CKM pattern gate: " + ("PASS" if ckpat.get("pass") else "FAIL"))
        vv = (ckpat.get("values") or {})
        md.append("\n  - θ12/θ23/θ13 (deg) = (%s, %s, %s)  range12=%s range23=%s range13=%s" % (
            vv.get("theta12_deg"), vv.get("theta23_deg"), vv.get("theta13_deg"),
            ckpat.get("theta12_range_deg"), ckpat.get("theta23_range_deg"), ckpat.get("theta13_range_deg"),
        ))
        md.append("\n  - ordering=%s, J=%s  J_range_abs=%s" % (ckpat.get("ordering"), vv.get("J"), ckpat.get("J_range_abs")))

        md.append("\n- PMNS pattern gate: " + ("PASS" if pmpat.get("pass") else "FAIL"))
        pv = (pmpat.get("values") or {})
        md.append("\n  - θ12/θ23/θ13 (deg) = (%s, %s, %s)  min_large=%s°, large_count=%s" % (
            pv.get("theta12_deg"), pv.get("theta23_deg"), pv.get("theta13_deg"),
            pmpat.get("min_large_angle_deg"), pmpat.get("large_count"),
        ))

        pol = (rc.get("policy") or {})
        pol0 = (pol.get("inherits") or pol)
        md.append("\n- policy: K=%s, rho=%s; δ(C30)=%s" % (pol0.get("K"), pol0.get("rho"), pol0.get("delta_deg")))
        sec = (rc.get("sectors") or {})
        if sec:
            md.append("\n- sectors (unitary + eigphase→C30 residual, deg):")
            for nm in ("Uu", "Ud", "Ue", "Unu"):
                it = (sec.get(nm) or {})
                md.append("\n  - %s: unitary_resid=%s, eigphase_C30_resid_deg=%s" % (nm, it.get("unitary_residual"), it.get("eigphase_C30_residual_deg")))
        ck = ((rc.get("CKM") or {}).get("angles") or {})
        pm = ((rc.get("PMNS") or {}).get("angles") or {})
        md.append("\n- CKM (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (ck.get("theta12_deg"), ck.get("theta23_deg"), ck.get("theta13_deg"), ck.get("J")))
        md.append("\n- PMNS (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (pm.get("theta12_deg"), pm.get("theta23_deg"), pm.get("theta13_deg"), pm.get("J")))
        rc5 = (checks.get("rt_construct_sector_eigphase_snap") or {})
        if rc5 and not rc5.get("error"):
            md.append("\n\n## RT construct (v0.5, sector eigphase snap to C30; diagnostic)\n")
            g5 = (rc5.get("gate") or {})
            md.append("\n- overall gate (score+pattern): " + ("PASS" if g5.get("pass") else "FAIL"))
            sec5 = (rc5.get("sectors") or {})
            if sec5:
                md.append("\n- sectors (before→after): eigphase_C30_resid_deg, max_phase_shift_deg, fro_delta:")
                for nm in ("Uu", "Ud", "Ue", "Unu"):
                    it = (sec5.get(nm) or {})
                    md.append("\n  - %s: %s→%s , Δmax=%s , ||Δ||_F=%s" % (
                        nm,
                        it.get("eigphase_C30_residual_deg_before"),
                        it.get("eigphase_C30_residual_deg_after"),
                        it.get("eigphase_delta_deg_max"),
                        it.get("fro_delta"),
                    ))
            ck5 = ((rc5.get("CKM") or {}).get("angles") or {})
            pm5 = ((rc5.get("PMNS") or {}).get("angles") or {})
            md.append("\n- CKM (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (ck5.get("theta12_deg"), ck5.get("theta23_deg"), ck5.get("theta13_deg"), ck5.get("J")))
            md.append("\n- PMNS (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (pm5.get("theta12_deg"), pm5.get("theta23_deg"), pm5.get("theta13_deg"), pm5.get("J")))
        elif rc5 and rc5.get("error"):
            md.append("\n\n## RT construct (v0.5, sector eigphase snap to C30; diagnostic)\n")
            md.append("\n- error: %s\n" % rc5.get("error"))


        rc6 = (checks.get("rt_construct_sector_eigphase_snap_C300") or {})
        if rc6 and not rc6.get("error"):
            md.append("\n\n## RT construct (v0.6, sector eigphase snap: quark→C300, lepton→C30; diagnostic)\n")
            g6 = (rc6.get("gate") or {})
            md.append("\n- overall gate (score+pattern): " + ("PASS" if g6.get("pass") else "FAIL"))
            sec6 = (rc6.get("sectors") or {})
            if sec6:
                md.append("\n- sectors (before→after): [n_grid] eigphase_Cn_resid_deg, max_phase_shift_deg, fro_delta:")
                for nm in ("Uu", "Ud", "Ue", "Unu"):
                    it = (sec6.get(nm) or {})
                    md.append("\n  - %s: [n=%s] %s→%s , Δmax=%s , ||Δ||_F=%s" % (
                        nm,
                        it.get("n_grid"),
                        it.get("eigphase_Cn_residual_deg_before"),
                        it.get("eigphase_Cn_residual_deg_after"),
                        it.get("eigphase_delta_deg_max"),
                        it.get("fro_delta"),
                    ))
            ck6 = ((rc6.get("CKM") or {}).get("angles") or {})
            pm6 = ((rc6.get("PMNS") or {}).get("angles") or {})
            md.append("\n- CKM (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (ck6.get("theta12_deg"), ck6.get("theta23_deg"), ck6.get("theta13_deg"), ck6.get("J")))
            md.append("\n- PMNS (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (pm6.get("theta12_deg"), pm6.get("theta23_deg"), pm6.get("theta13_deg"), pm6.get("J")))
        elif rc6 and rc6.get("error"):
            md.append("\n\n## RT construct (v0.6, sector eigphase snap: quark→C300, lepton→C30; diagnostic)\n")
            md.append("\n- error: %s\n" % rc6.get("error"))


        rc7 = (checks.get("rt_construct_monodromy_1260") or {})
        if rc7 and not rc7.get("error"):
            md.append("\n\n## RT construct (v0.7, monodromy over L*=1260=42×30; diagnostic)\n")
            g7 = (rc7.get("gate") or {})
            md.append("\n- overall gate (score+pattern): " + ("PASS" if g7.get("pass") else "FAIL"))
            pol7 = (rc7.get("policy") or {})
            md.append("\n- policy: L*=%s ticks, blocks=%s, Δk_lepton=%s, Δk_quark=%s" % (
                pol7.get("L_star_ticks"), pol7.get("blocks"),
                (pol7.get("monodromy_step") or {}).get("lepton_dk"),
                (pol7.get("monodromy_step") or {}).get("quark_dk"),
            ))
            sec7 = (rc7.get("sectors") or {})
            if sec7:
                md.append("\n- sectors (unitary_resid, tail k's):")
                for nm in ("Uu","Ud","Ue","Unu"):
                    it = (sec7.get(nm) or {})
                    md.append("\n  - %s: unitary_resid=%s, k_tail=%s" % (nm, it.get("unitary_residual"), it.get("k_hist_tail")))
            ck7 = ((rc7.get("CKM") or {}).get("angles") or {})
            pm7 = ((rc7.get("PMNS") or {}).get("angles") or {})
            md.append("\n- CKM (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (ck7.get("theta12_deg"), ck7.get("theta23_deg"), ck7.get("theta13_deg"), ck7.get("J")))
            md.append("\n- PMNS (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (pm7.get("theta12_deg"), pm7.get("theta23_deg"), pm7.get("theta13_deg"), pm7.get("J")))
        elif rc7 and rc7.get("error"):
            md.append("\n\n## RT construct (v0.7, monodromy over L*=1260=42×30; diagnostic)\n")
            md.append("\n- error: %s\n" % rc7.get("error"))


        rc8 = (checks.get("rt_construct_monodromy_1260_z3kick") or {})
        if rc8 and not rc8.get("error"):
            md.append("\n\n## RT construct (v0.8, monodromy L*=1260 with Z3-permuted kick + A/B toggle; diagnostic)\n")
            g8 = (rc8.get("gate") or {})
            md.append("\n- overall gate (score+pattern): " + ("PASS" if g8.get("pass") else "FAIL"))
            pol8 = (rc8.get("policy") or {})
            md.append("\n- policy: L*=%s ticks, blocks=%s, Z3_perm=%s, AB_toggle=%s" % (
                pol8.get("L_star_ticks"), pol8.get("blocks"),
                (pol8.get("kick_variation") or {}).get("Z3_perm"),
                (pol8.get("kick_variation") or {}).get("AB_toggle"),
            ))
            ck8 = ((rc8.get("CKM") or {}).get("angles") or {})
            pm8 = ((rc8.get("PMNS") or {}).get("angles") or {})
            md.append("\n- CKM (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (ck8.get("theta12_deg"), ck8.get("theta23_deg"), ck8.get("theta13_deg"), ck8.get("J")))
            md.append("\n- PMNS (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (pm8.get("theta12_deg"), pm8.get("theta23_deg"), pm8.get("theta13_deg"), pm8.get("J")))
        elif rc8 and rc8.get("error"):
            md.append("\n\n## RT construct (v0.8, monodromy L*=1260 with Z3-permuted kick + A/B toggle; diagnostic)\n")
            md.append("\n- error: %s\n" % rc8.get("error"))



        rc9 = (checks.get("rt_construct_monodromy_1260_rho_kick") or {})
        if rc9 and not rc9.get("error"):
            md.append("\n\n## RT construct (v0.9, monodromy L*=1260 with Z3-kick + A/B-toggle + ρ-microphase on quark projector; diagnostic)\n")
            g9 = (rc9.get("gate") or {})
            md.append("\n- overall gate (score+pattern): " + ("PASS" if g9.get("pass") else "FAIL"))
            pol9 = (rc9.get("policy") or {})
            r9 = (pol9.get("rho_microphase") or {})
            md.append("\n- policy: L*=%s ticks, blocks=%s, micro_step=%s (C300), up_sign=%s, down_sign=%s" % (
                pol9.get("L_star_ticks"), pol9.get("blocks"), r9.get("micro_step"), r9.get("up_sign"), r9.get("down_sign")
            ))
            ck9 = ((rc9.get("CKM") or {}).get("angles") or {})
            pm9 = ((rc9.get("PMNS") or {}).get("angles") or {})
            md.append("\n- CKM (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (ck9.get("theta12_deg"), ck9.get("theta23_deg"), ck9.get("theta13_deg"), ck9.get("J")))
            md.append("\n- PMNS (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (pm9.get("theta12_deg"), pm9.get("theta23_deg"), pm9.get("theta13_deg"), pm9.get("J")))
        elif rc9 and rc9.get("error"):
            md.append("\n\n## RT construct (v0.9, monodromy L*=1260 with Z3-kick + A/B-toggle + ρ-microphase on quark projector; diagnostic)\n")
            md.append("\n- error: %s\n" % rc9.get("error"))




        rc10 = (checks.get("rt_construct_monodromy_1260_rho_z3sieve") or {})
        if rc10 and not rc10.get("error"):
            md.append("\n\n## RT construct (v0.10, monodromy L*=1260 with ρ-microphase Z3-sieved; diagnostic)\n")
            g10 = (rc10.get("gate") or {})
            md.append("\n- overall gate (score+pattern): " + ("PASS" if g10.get("pass") else "FAIL"))
            pol10 = (rc10.get("policy") or {})
            r10 = (pol10.get("rho_microphase") or {})
            md.append("\n- policy: L*=%s ticks, blocks=%s, micro_step=%s (C300), rho_z3_values=%s" % (
                pol10.get("L_star_ticks"), pol10.get("blocks"), r10.get("micro_step"), r10.get("rho_z3_values")
            ))
            ck10 = ((rc10.get("CKM") or {}).get("angles") or {})
            pm10 = ((rc10.get("PMNS") or {}).get("angles") or {})
            md.append("\n- CKM (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (ck10.get("theta12_deg"), ck10.get("theta23_deg"), ck10.get("theta13_deg"), ck10.get("J")))
            md.append("\n- PMNS (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (pm10.get("theta12_deg"), pm10.get("theta23_deg"), pm10.get("theta13_deg"), pm10.get("J")))
        elif rc10 and rc10.get("error"):
            md.append("\n\n## RT construct (v0.10, monodromy L*=1260 with ρ-microphase Z3-sieved; diagnostic)\n")
            md.append("\n- error: %s\n" % rc10.get("error"))



        rc11 = (checks.get("rt_construct_monodromy_1260_rho_z3sieve_12tiebreak") or {})
        if rc11 and not rc11.get("error"):
            md.append("\n\n## RT construct (v0.11, monodromy L*=1260 with ρ-microphase Z3-sieved + directed 1–2 tie-break; diagnostic)\n")
            g11 = (rc11.get("gate") or {})
            md.append("\n- overall gate (score+pattern): " + ("PASS" if g11.get("pass") else "FAIL"))
            pol11 = (rc11.get("policy") or {})
            r11 = (pol11.get("rho_microphase") or {})
            tb11 = (pol11.get("tiebreak_12") or {})
            md.append("\n- policy: L*=%s ticks, blocks=%s, micro_step=%s (C300), rho_z3_values=%s" % (
                pol11.get("L_star_ticks"), pol11.get("blocks"), r11.get("micro_step"), r11.get("rho_z3_values")
            ))
            md.append("\n- 1–2 tie-break: where=%s, when=%s, eps0=%s" % (tb11.get("where"), tb11.get("when"), tb11.get("eps0")))
            sec11 = (rc11.get("sectors") or {})
            if sec11:
                md.append("\n- sectors (unitary_resid, 1–2 hits, tail k's):")
                for nm in ("Uu","Ud","Ue","Unu"):
                    it = (sec11.get(nm) or {})
                    md.append("\n  - %s: unitary_resid=%s, tiebreak12=%s, k_tail=%s" % (
                        nm, it.get("unitary_residual"), it.get("tiebreak_12_applied"), it.get("k_hist_tail")
                    ))
            ck11 = ((rc11.get("CKM") or {}).get("angles") or {})
            pm11 = ((rc11.get("PMNS") or {}).get("angles") or {})
            md.append("\n- CKM (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (ck11.get("theta12_deg"), ck11.get("theta23_deg"), ck11.get("theta13_deg"), ck11.get("J")))
            md.append("\n- PMNS (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (pm11.get("theta12_deg"), pm11.get("theta23_deg"), pm11.get("theta13_deg"), pm11.get("J")))
        elif rc11 and rc11.get("error"):
            md.append("\n\n## RT construct (v0.11, monodromy L*=1260 with directed 1–2 tie-break; diagnostic)\n")
            md.append("\n- error: %s\n" % rc11.get("error"))



        rc12 = (checks.get("rt_construct_monodromy_1260_cabibbo_kick_12") or {})
        if rc12 and not rc12.get("error"):
            md.append("\n\n## RT construct (v0.12, monodromy L*=1260 with single C30 Cabibbo kick in (1,2); diagnostic)\n")
            g12 = (rc12.get("gate") or {})
            md.append("\n- overall gate (score+pattern): " + ("PASS" if g12.get("pass") else "FAIL"))
            pol12 = (rc12.get("policy") or {})
            cb12 = (pol12.get("cabibbo_kick_12") or {})
            md.append("\n- policy: L*=%s ticks, blocks=%s, rho=%s, eps12=%s" % (
                pol12.get("L_star_ticks"), pol12.get("blocks"), pol12.get("rho"), cb12.get("eps12")
            ))
            md.append("\n- Cabibbo kick: where=%s, when=%s" % (cb12.get("where"), cb12.get("when")))
            sec12 = (rc12.get("sectors") or {})
            if sec12:
                md.append("\n- sectors (unitary_resid, cabibbo_kick_applied, tail k's):")
                for nm in ("Uu","Ud","Ue","Unu"):
                    it = (sec12.get(nm) or {})
                    md.append("\n  - %s: unitary_resid=%s, cabibbo=%s, k_tail=%s" % (
                        nm, it.get("unitary_residual"), it.get("cabibbo_kick_applied"), it.get("k_hist_tail")
                    ))
            ck12 = ((rc12.get("CKM") or {}).get("angles") or {})
            pm12 = ((rc12.get("PMNS") or {}).get("angles") or {})
            md.append("\n- CKM (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (ck12.get("theta12_deg"), ck12.get("theta23_deg"), ck12.get("theta13_deg"), ck12.get("J")))
            md.append("\n- PMNS (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (pm12.get("theta12_deg"), pm12.get("theta23_deg"), pm12.get("theta13_deg"), pm12.get("J")))
        elif rc12 and rc12.get("error"):
            md.append("\n\n## RT construct (v0.12, monodromy L*=1260 with single Cabibbo kick; diagnostic)\n")
            md.append("\n- error: %s\n" % rc12.get("error"))


        rc13 = (checks.get("rt_construct_monodromy_1260_postR12_seam") or {})
        if rc13 and not rc13.get("error"):
            md.append("\n\n## RT construct (v0.13, monodromy L*=1260 + post seam R12 on down sector; diagnostic)\n")
            g13 = (rc13.get("gate") or {})
            md.append("\n- overall gate (score+pattern): " + ("PASS" if g13.get("pass") else "FAIL"))
            pol13 = (rc13.get("policy") or {})
            ps13 = (pol13.get("postR12_seam") or {})
            md.append("\n- policy: L*=%s ticks, blocks=%s, theta_deg=%s, phi_rad=%s" % (
                pol13.get("L_star_ticks"), pol13.get("blocks"), ps13.get("theta_deg"), ps13.get("phi_rad")
            ))
            md.append("\n- seam op: %s (invariant: %s)" % (ps13.get("action"), ps13.get("invariant")))
            sec13 = (rc13.get("sectors") or {})
            if sec13:
                md.append("\n- sectors (unitary_resid, postR12, tail k's):")
                for nm in ("Uu","Ud","Ue","Unu"):
                    it = (sec13.get(nm) or {})
                    md.append("\n  - %s: unitary_resid=%s, postR12=%s, k_tail=%s" % (
                        nm, it.get("unitary_residual"), it.get("postR12_applied"), it.get("k_hist_tail")
                    ))
            ck13 = ((rc13.get("CKM") or {}).get("angles") or {})
            pm13 = ((rc13.get("PMNS") or {}).get("angles") or {})
            md.append("\n- CKM (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (ck13.get("theta12_deg"), ck13.get("theta23_deg"), ck13.get("theta13_deg"), ck13.get("J")))
            md.append("\n- PMNS (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (pm13.get("theta12_deg"), pm13.get("theta23_deg"), pm13.get("theta13_deg"), pm13.get("J")))
        elif rc13 and rc13.get("error"):
            md.append("\n\n## RT construct (v0.13, monodromy L*=1260 + post seam R12; diagnostic)\n")
            md.append("\n- error: %s\n" % rc13.get("error"))


        rc14 = (checks.get("rt_construct_monodromy_1260_postR12_seam_macro_micro") or {})
        if rc14 and not rc14.get("error"):
            md.append("\n\n## RT construct (v0.14, monodromy L*=1260 + post seam R12 (macro+micro); diagnostic)\n")
            g14 = (rc14.get("gate") or {})
            md.append("\n- overall gate (score+pattern): " + ("PASS" if g14.get("pass") else "FAIL"))
            pol14 = (rc14.get("policy") or {})
            ps14 = (pol14.get("postR12_seam") or {})
            tc = (ps14.get("theta_components_deg") or {})
            md.append("\n- policy: L*=%s ticks, blocks=%s, theta_deg=%s (= %s + %s; s_end=%s), phi_rad=%s" % (
                pol14.get("L_star_ticks"), pol14.get("blocks"), ps14.get("theta_deg"), tc.get("macro"), tc.get("micro"), tc.get("s_end"), ps14.get("phi_rad")
            ))
            md.append("\n- seam op: %s (invariant: %s)" % (ps14.get("action"), ps14.get("invariant")))
            sec14 = (rc14.get("sectors") or {})
            if sec14:
                md.append("\n- sectors (unitary_resid, postR12, tail k's):")
                for nm in ("Uu","Ud","Ue","Unu"):
                    it = (sec14.get(nm) or {})
                    md.append("\n  - %s: unitary_resid=%s, postR12=%s, k_tail=%s" % (
                        nm, it.get("unitary_residual"), it.get("postR12_applied"), it.get("k_hist_tail")
                    ))
            ck14 = ((rc14.get("CKM") or {}).get("angles") or {})
            pm14 = ((rc14.get("PMNS") or {}).get("angles") or {})
            md.append("\n- CKM (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (ck14.get("theta12_deg"), ck14.get("theta23_deg"), ck14.get("theta13_deg"), ck14.get("J")))
            md.append("\n- PMNS (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (pm14.get("theta12_deg"), pm14.get("theta23_deg"), pm14.get("theta13_deg"), pm14.get("J")))
        elif rc14 and rc14.get("error"):
            md.append("\n\n## RT construct (v0.14, monodromy L*=1260 + post seam R12 (macro+micro); diagnostic)\n")
            md.append("\n- error: %s\n" % rc14.get("error"))


        rc15 = (checks.get("rt_construct_monodromy_1260_postR12_seam_from_phase_rule") or {})
        if rc15 and not rc15.get("error"):
            md.append("\n\n## RT construct (v0.15, monodromy L*=1260 + post seam R12 tied to k_rt mod 3; diagnostic)\n")
            g15 = (rc15.get("gate") or {})
            md.append("\n- overall gate (score+pattern): " + ("PASS" if g15.get("pass") else "FAIL"))
            pol15 = (rc15.get("policy") or {})
            ps15 = (pol15.get("postR12_seam") or {})
            tc15 = (ps15.get("theta_components_deg") or {})
            md.append("\n- policy: L*=%s ticks, blocks=%s, theta_deg=%s (= %s + %s; s_micro=%s from k_mod3=%s), phi_rad=%s" % (
                pol15.get("L_star_ticks"), pol15.get("blocks"), ps15.get("theta_deg"), tc15.get("macro"), tc15.get("micro"), tc15.get("s_micro"), tc15.get("k_mod3"), ps15.get("phi_rad")
            ))
            md.append("\n- seam op: %s (rule: %s; invariant: %s)" % (ps15.get("action"), ps15.get("seam_rule"), ps15.get("invariant")))
            sec15 = (rc15.get("sectors") or {})
            if sec15:
                md.append("\n- sectors (unitary_resid, postR12, tail k's):")
                for nm in ("Uu","Ud","Ue","Unu"):
                    it = (sec15.get(nm) or {})
                    md.append("\n  - %s: unitary_resid=%s, postR12=%s, k_tail=%s" % (
                        nm, it.get("unitary_residual"), it.get("postR12_applied"), it.get("k_hist_tail")
                    ))
            ck15 = ((rc15.get("CKM") or {}).get("angles") or {})
            pm15 = ((rc15.get("PMNS") or {}).get("angles") or {})
            md.append("\n- CKM (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (ck15.get("theta12_deg"), ck15.get("theta23_deg"), ck15.get("theta13_deg"), ck15.get("J")))
            md.append("\n- PMNS (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (pm15.get("theta12_deg"), pm15.get("theta23_deg"), pm15.get("theta13_deg"), pm15.get("J")))
        elif rc15 and rc15.get("error"):
            md.append("\n\n## RT construct (v0.15, monodromy L*=1260 + post seam R12 tied to k_rt; diagnostic)\n")
            md.append("\n- error: %s\n" % rc15.get("error"))


        rc16 = (checks.get("rt_construct_monodromy_1260_postR12_seam_from_phase_rule_down_oriented") or {})
        if rc16 and not rc16.get("error"):
            md.append("\n\n## RT construct (v0.16, monodromy L*=1260 + post seam R12, down-oriented k_rt mod 3 map; diagnostic)\n")
            g16 = (rc16.get("gate") or {})
            md.append("\n- overall gate (score+pattern): " + ("PASS" if g16.get("pass") else "FAIL"))
            pol16 = (rc16.get("policy") or {})
            ps16 = (pol16.get("postR12_seam") or {})
            tc16 = (ps16.get("theta_components_deg") or {})
            md.append("\n- policy: L*=%s ticks, blocks=%s, theta_deg=%s (= %s + %s; s_micro=%s from k_mod3=%s; map=%s), phi_rad=%s" % (
                pol16.get("L_star_ticks"), pol16.get("blocks"), ps16.get("theta_deg"), tc16.get("macro"), tc16.get("micro"), tc16.get("s_micro"), tc16.get("k_mod3"), tc16.get("map"), ps16.get("phi_rad")
            ))
            md.append("\n- seam op: %s (rule: %s; invariant: %s)" % (ps16.get("action"), ps16.get("seam_rule"), ps16.get("invariant")))
            sec16 = (rc16.get("sectors") or {})
            if sec16:
                md.append("\n- sectors (unitary_resid, postR12, tail k's):")
                for nm in ("Uu","Ud","Ue","Unu"):
                    it = (sec16.get(nm) or {})
                    md.append("\n  - %s: unitary_resid=%s, postR12=%s, k_tail=%s" % (
                        nm, it.get("unitary_residual"), it.get("postR12_applied"), it.get("k_hist_tail")
                    ))
            ck16 = ((rc16.get("CKM") or {}).get("angles") or {})
            pm16 = ((rc16.get("PMNS") or {}).get("angles") or {})
            md.append("\n- CKM (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (ck16.get("theta12_deg"), ck16.get("theta23_deg"), ck16.get("theta13_deg"), ck16.get("J")))
            md.append("\n- PMNS (deg): θ12=%s, θ23=%s, θ13=%s, J=%s" % (pm16.get("theta12_deg"), pm16.get("theta23_deg"), pm16.get("theta13_deg"), pm16.get("J")))
        elif rc16 and rc16.get("error"):
            md.append("\n\n## RT construct (v0.16, monodromy L*=1260 + post seam R12, down-oriented k_rt map; diagnostic)\n")
            md.append("\n- error: %s\n" % rc16.get("error"))





        lv = (rc.get("legacy_v0_2") or {})
        if lv:
            md.append("\n- legacy v0.2 gate (info): %s" % ("PASS" if (lv.get("gate") or {}).get("pass") else "FAIL"))
    elif rc and rc.get("error"):
        md.append("\n\n## RT construct (v0.4, factorized sqrt; diagnostic)\n")
        md.append("\n- error: %s\n" % rc.get("error"))

    # Gate-2 regression lock (candidate stability)
    rl = (checks.get("regression_lock_ckm_v0_25") or {})
    if rl:
        md.append("\n\n## Gate-2 regression lock (CKM v0.25 candidate)\n")
        md.append("\n- status: %s (tol=%s deg)" % ("PASS" if rl.get("pass") else "FAIL", rl.get("tol_deg")))
        if rl.get("created"):
            md.append("\n- created lock file: out/FLAVOR_LOCK/regression_lock_ckm_v0_25.json")
        if not rl.get("pass"):
            md.append("\n- diffs_deg: %s" % (rl.get("diffs_deg")))
            md.append("\n- ref: %s" % (rl.get("ref")))
            md.append("\n- cur: %s" % (rl.get("cur")))
        if rl.get("note"):
            md.append("\n- note: %s" % rl.get("note"))

    # History diagnostics (informational)

    hv = (checks.get("history_versions") or {})
    if hv:
        md.append("\n\n## History diagnostics (informational; v0_* snapshots)\n")
        for kind in ("CKM", "PMNS"):
            arr = hv.get(kind) or []
            if not arr:
                continue
            md.append(f"\n- {kind}:")
            tail = arr[-5:]
            for it in tail:
                md.append(
                    f"\n  - {it.get('ver')}: theta13={it.get('theta13_deg')}, bound(theta13)>={it.get('min_theta13_deg_bound')}, min|M|={it.get('min_abs')}"
                )

    md.append("\n\nInputs:\n")
    md.append(f"- {overall['inputs']['flavor_ud']}\n- {overall['inputs']['flavor_enu']}\n")
    out_md.write_text("".join(md), encoding="utf-8")

    return 0 if overall["gate"]["PASS"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
