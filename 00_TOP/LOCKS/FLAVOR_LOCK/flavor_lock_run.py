#!/usr/bin/env python3
"""FLAVOR_LOCK runner (v0.9).

v0.9 delta (vs v0.8)
  - v0.8 gav icke-trivial CKM/PMNS via hårdare par-gates, men kunde ändå välja
    en "hörnlösning" där t.ex. d-sektorns m1/m2 blev extremt liten (~1e-7).
  - v0.9 lägger därför in en *sanity-penalty* mot "absurda" hierarkier:
      * Behåll preferensen för små ratios (hierarki), men straffa om ratios
        går under ett diskret golv (default 1e-4) i laddade sektorer.
  - Ingen ny kontinuerlig parameter exponeras; allt är hårdkodat och deterministiskt.

Allt är deterministiskt och dimensionslöst. Inga SI-tal.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple, Optional

import numpy as np


def repo_root_from_here(here: Path) -> Path:
    # here = .../00_TOP/LOCKS/FLAVOR_LOCK/flavor_lock_run.py
    return here.resolve().parents[3]


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def write_json(p: Path, obj: dict) -> None:
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8")


def circulant(c0: int, c1: int, c2: int) -> np.ndarray:
    # [[c0,c1,c2],[c2,c0,c1],[c1,c2,c0]]
    return np.array([[c0, c1, c2], [c2, c0, c1], [c1, c2, c0]], dtype=np.complex128)


def near_coupling(p: int) -> np.ndarray:
    """Discrete near-coupling patterns.

    p=1..4 are the original v0.1 patterns (some are circulant-like).
    p=5..6 are the v0.2 non-circulant patterns.
    """
    M = np.zeros((3, 3), dtype=np.complex128)

    if p == 1:
        M[0, 1] = 1
        M[1, 0] = 1
    elif p == 2:
        M[1, 2] = 1
        M[2, 1] = 1
    elif p == 3:
        M[0, 2] = 1
        M[2, 0] = 1
    elif p == 4:
        # directed 1->2->3->1
        M[0, 1] = 1
        M[1, 2] = 1
        M[2, 0] = 1
    elif p == 5:
        # symmetric chain 1--2--3
        M[0, 1] = 1
        M[1, 0] = 1
        M[1, 2] = 1
        M[2, 1] = 1
    elif p == 6:
        # directed chain 1->2->3
        M[0, 1] = 1
        M[1, 2] = 1
    else:
        raise ValueError("p must be 1..6")

    return M


def apply_edge_phases(N: np.ndarray, phi: float) -> np.ndarray:
    """Inject a discrete internal phase into edges.

    For each non-zero entry N[i,j], multiply by exp(i*phi*(i-j)).
    This makes symmetric edges conjugate-paired automatically.

    Important: This is *not* a similarity transform, so it can generate
    non-removable phases (CP structure) in the left-Hermitian H=M M†.
    """
    if abs(phi) < 1e-15:
        return N
    out = N.astype(np.complex128).copy()
    for i in range(3):
        for j in range(3):
            if out[i, j] != 0:
                out[i, j] = out[i, j] * np.exp(1j * phi * float(i - j))
    return out


def proj_phase(n: int, s: int, k: int) -> np.ndarray:
    """A small, deterministic diagonal phase projector (discrete gauge)."""
    if n <= 0:
        raise ValueError("n must be >=1")
    twopi = 2.0 * math.pi
    ph = [twopi * (s + j * k) / n for j in range(3)]
    return np.diag([np.exp(1j * a) for a in ph]).astype(np.complex128)


def perm_mats() -> Dict[str, np.ndarray]:
    def P(idx: Tuple[int, int, int]) -> np.ndarray:
        M = np.zeros((3, 3), dtype=np.complex128)
        for r, c in enumerate(idx):
            M[r, c] = 1
        return M

    return {
        "id": P((0, 1, 2)),
        "swap12": P((1, 0, 2)),
        "swap23": P((0, 2, 1)),
        "swap13": P((2, 1, 0)),
        "cyc123": P((1, 2, 0)),
        "cyc132": P((2, 0, 1)),
    }


def diagonalize_yukawa(M: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Return (masses, U) from H=M M†.

    masses are sqrt(eigvals) sorted ascending.
    U columns correspond to eigenvectors.
    """
    H = M @ M.conjugate().T
    w, v = np.linalg.eigh(H)
    w = np.maximum(w.real, 0.0)
    idx = np.argsort(w)
    w = w[idx]
    v = v[:, idx]
    m = np.sqrt(w)
    return m, v


def jarlskog(V: np.ndarray) -> float:
    return float(np.imag(V[0, 0] * V[1, 1] * np.conjugate(V[0, 1]) * np.conjugate(V[1, 0])))


def extract_angles(V: np.ndarray) -> Dict[str, float]:
    """Approx PDG angles from a unitary 3x3 matrix.

    Uses absolute values; phase conventions ignored.
    Returns angles in radians/deg and J.
    """
    eps = 1e-15
    s13 = float(np.clip(abs(V[0, 2]), 0.0, 1.0))
    c13 = math.sqrt(max(1.0 - s13 * s13, 0.0))
    if c13 < eps:
        s12 = 0.0
        s23 = 0.0
    else:
        s12 = float(np.clip(abs(V[0, 1]) / c13, 0.0, 1.0))
        s23 = float(np.clip(abs(V[1, 2]) / c13, 0.0, 1.0))

    th13 = math.asin(s13)
    th12 = math.asin(s12)
    th23 = math.asin(s23)

    J = jarlskog(V)

    # A derived delta estimate via sin(delta) (optional, not used as a fit target).
    c12 = math.sqrt(max(1.0 - s12 * s12, 0.0))
    c23 = math.sqrt(max(1.0 - s23 * s23, 0.0))
    denom = c12 * c23 * (c13 ** 2) * s12 * s23 * s13
    if abs(denom) < 1e-14:
        sin_delta = 0.0
        delta = 0.0
    else:
        sin_delta = float(np.clip(J / denom, -1.0, 1.0))
        delta = math.asin(sin_delta)

    return {
        "theta12_rad": th12,
        "theta23_rad": th23,
        "theta13_rad": th13,
        "theta12_deg": th12 * 180.0 / math.pi,
        "theta23_deg": th23 * 180.0 / math.pi,
        "theta13_deg": th13 * 180.0 / math.pi,
        "J": J,
        "delta_rad_from_sin": delta,
        "delta_deg_from_sin": delta * 180.0 / math.pi,
        "sin_delta": sin_delta,
    }


def charged_hierarchy_sanity_penalty(r12: float, r23: float) -> float:
    """Soft penalty against *absurdly* strong hierarchy in charged sectors.

    We still prefer small ratios (hierarchy), but do not want corner-solutions where
    r12 or r23 collapses numerically to extremely tiny values without any extra RT reason.

    Implemented as a log-distance penalty below fixed floors.
    """

    # Hard-coded floors (dimensionless). Chosen to only activate on extreme corner cases.
    floor12 = 1e-4
    floor23 = 1e-4
    w = 10.0

    def pen(r: float, floor: float) -> float:
        if r >= floor:
            return 0.0
        r_eff = max(r, 1e-30)
        d = math.log10(floor / r_eff)
        return w * d * d

    return pen(r12, floor12) + pen(r23, floor23)


@dataclass(frozen=True)
class SectorChoice:
    c0: int
    c1: int
    c2: int
    n: int
    s: int
    k: int
    p: int
    q: int  # discrete CP phase index
    pi: str


@dataclass(frozen=True)
class SectorResult:
    choice: SectorChoice
    masses: Tuple[float, float, float]
    ratios: Tuple[float, float]
    U: np.ndarray
    cost: float


def build_M(choice: SectorChoice, eps_nc: float = 0.15) -> np.ndarray:
    C = circulant(choice.c0, choice.c1, choice.c2)
    N0 = near_coupling(choice.p)

    # Discrete phase: q in {0..5} -> phi = 2π q / 6.
    phi = (2.0 * math.pi) * (choice.q % 6) / 6.0
    N = apply_edge_phases(N0, phi)

    P = proj_phase(choice.n, choice.s, choice.k)
    Pi = perm_mats()[choice.pi]

    # IMPORTANT: keep P as a discrete gauge, but inject CP via N itself (above).
    M = Pi.T @ (P @ (C + eps_nc * N) @ P.conjugate().T) @ Pi
    return M


def sector_scan(
    *,
    c_vals: Sequence[int],
    n_vals: Sequence[int],
    s_vals: Sequence[int],
    k_vals: Sequence[int],
    p_vals: Sequence[int],
    q_vals: Sequence[int],
    pi_names: Sequence[str],
    top: int,
    seed: int,
    eps_nc: float,
    prefer_strong_hierarchy: bool,
) -> List[SectorResult]:
    # NOTE: The scan must be seed-stable. We therefore avoid any RNG-based
    # tie-break. All ties are broken deterministically by a lexicographic key
    # on the discrete choice itself.
    results: List[SectorResult] = []

    def _choice_key(ch: SectorChoice) -> tuple:
        return (ch.c0, ch.c1, ch.c2, ch.n, ch.s, ch.k, ch.p, ch.q, ch.pi)

    for c0 in c_vals:
        for c1 in c_vals:
            for c2 in c_vals:
                if c0 == c1 == c2 == 0:
                    continue
                for n in n_vals:
                    for s in s_vals:
                        for k in k_vals:
                            for p in p_vals:
                                for q in q_vals:
                                    for pi in pi_names:
                                        ch = SectorChoice(c0, c1, c2, n, s, k, p, q, pi)
                                        try:
                                            M = build_M(ch, eps_nc=eps_nc)
                                            m, U = diagonalize_yukawa(M)
                                        except Exception:
                                            continue

                                        m1, m2, m3 = (float(m[0]), float(m[1]), float(m[2]))
                                        if m3 <= 0 or m2 <= 0:
                                            continue
                                        r12 = m1 / m2
                                        r23 = m2 / m3

                                        # Internal cost: encourage hierarchy (smaller ratios win), avoid degeneracy.
                                        base = (r12 * r12) + (r23 * r23)
                                        cost = base if prefer_strong_hierarchy else 0.25 * base

                                        # v0.9: avoid absurd corner-solutions in charged sectors.
                                        if prefer_strong_hierarchy:
                                            cost += charged_hierarchy_sanity_penalty(r12, r23)
                                        if abs(m2 - m1) / max(m2, 1e-12) < 1e-3:
                                            cost += 50.0
                                        if abs(m3 - m2) / max(m3, 1e-12) < 1e-3:
                                            cost += 50.0

                                        results.append(
                                            SectorResult(
                                                choice=ch,
                                                masses=(m1, m2, m3),
                                                ratios=(r12, r23),
                                                U=U,
                                                cost=cost,
                                            )
                                        )

    results.sort(key=lambda r: (r.cost, _choice_key(r.choice)))
    return results[: max(1, top)]


def pair_cost_ckm(Uu: np.ndarray, Ud: np.ndarray) -> Tuple[float, np.ndarray, Dict[str, float]]:
    V = Uu.conjugate().T @ Ud
    ang = extract_angles(V)

    th12 = float(ang["theta12_rad"])
    th23 = float(ang["theta23_rad"])
    th13 = float(ang["theta13_rad"])
    J = float(ang["J"])

    # Prefer small mixing, but do NOT allow collapse to trivial CKM.
    cost = th12 * th12 + th23 * th23 + th13 * th13

    # Floors (radians): enforce non-trivial θ12 & θ23, plus a non-zero |J|.
    th12_floor = 0.02   # ~1.15°
    th23_floor = 0.01   # ~0.57°
    th13_floor = 0.003  # ~0.17°
    J_floor = 1e-6

    def floor_pen(th: float, floor: float, base: float, w: float) -> float:
        if th >= floor:
            return 0.0
        d = floor - th
        return base + w * d * d

    cost += floor_pen(th12, th12_floor, base=5.0, w=200.0)
    cost += floor_pen(th23, th23_floor, base=5.0, w=200.0)
    cost += floor_pen(th13, th13_floor, base=1.0, w=50.0)

    if abs(J) < J_floor:
        d = J_floor - abs(J)
        cost += 5.0 + 1e6 * d * d

    # avoid exact trivial
    if cost < 1e-12:
        cost += 1e6

    return float(cost), V, ang



def pair_cost_pmns(Ue: np.ndarray, Unu: np.ndarray) -> Tuple[float, np.ndarray, Dict[str, float]]:
    U = Ue.conjugate().T @ Unu
    ang = extract_angles(U)

    th12 = float(ang["theta12_rad"])
    th23 = float(ang["theta23_rad"])
    th13 = float(ang["theta13_rad"])
    J = float(ang["J"])

    def under(th: float, floor: float) -> float:
        return max(0.0, floor - th)

    # Prefer non-trivial PMNS, no external targets.
    cost = under(th12, 0.10) ** 2 + under(th23, 0.10) ** 2 + under(th13, 0.05) ** 2

    if th13 < 1e-3:
        cost += 0.25
    if th23 < 1e-3:
        cost += 0.25

    if abs(J) < 1e-10:
        cost += 0.10

    return float(cost), U, ang



def _ratios_too_close(a12: float, a23: float, b12: float, b23: float, rel: float = 1e-3) -> bool:
    def close(x: float, y: float) -> bool:
        return abs(x - y) <= rel * max(abs(x), abs(y), 1e-12)
    return close(a12, b12) and close(a23, b23)

def run_ud(*, full: bool, top: int, seed: int) -> dict:
    pis = list(perm_mats().keys())

    # Base scan sizes
    if full:
        c_vals = [-2, -1, 0, 1, 2]
        n_vals = [1, 2, 3, 4]
    else:
        c_vals = [-1, 0, 1]
        n_vals = [2, 3, 4]

    s_vals = [0, 1, 2]
    k_vals = [0, 1, 2]

    # Charge-class dependent discrete spaces
    if full:
        q_vals_u = [1, 2, 4, 5]  # ±60°, ±120°
        q_vals_d = [0, 1, 3, 5]  # 0°, ±60°, 180°
    else:
        q_vals_u = [2, 4]
        q_vals_d = [1, 5]

    p_vals_u = [1, 2, 4, 5, 6]
    p_vals_d = [1, 3, 4, 5, 6]

    # Discrete isospin sign on near-coupling contribution
    eps0 = 0.15
    eps_u = +eps0
    eps_d = -eps0

    U_cands = sector_scan(
        c_vals=c_vals,
        n_vals=n_vals,
        s_vals=s_vals,
        k_vals=k_vals,
        p_vals=p_vals_u,
        q_vals=q_vals_u,
        pi_names=pis,
        top=top,
        seed=seed,
        eps_nc=eps_u,
        prefer_strong_hierarchy=True,
    )
    D_cands = sector_scan(
        c_vals=c_vals,
        n_vals=n_vals,
        s_vals=s_vals,
        k_vals=k_vals,
        p_vals=p_vals_d,
        q_vals=q_vals_d,
        pi_names=pis,
        top=top,
        seed=seed + 1,
        eps_nc=eps_d,
        prefer_strong_hierarchy=True,
    )

    best_total: Optional[float] = None
    best_payload = None
    deg_penalty = 25.0  # fixed gate penalty

    for u in U_cands:
        for d in D_cands:
            mix_cost, V, ang = pair_cost_ckm(u.U, d.U)
            total = u.cost + d.cost + 0.5 * mix_cost

            # v0.7 gate: forbid isospectral u/d.
            if _ratios_too_close(u.ratios[0], u.ratios[1], d.ratios[0], d.ratios[1]):
                total += deg_penalty

            if best_total is None or total < best_total:
                best_total = total
                best_payload = (u, d, V, ang, total)

    assert best_payload is not None
    u, d, V, ang, total = best_payload

    # NEG: trivial-mix (same sector)
    V_triv = u.U.conjugate().T @ u.U
    triv_ang = extract_angles(V_triv)

    return {
        "version": "v0.9",
        "scan": {
            "full": full,
            "top": top,
            "seed": seed,
            "tiebreak": "cost_then_choice_lex_v0_1",
            "eps0": eps0,
            "deg_gate_rel": 1e-3,
            "deg_gate_penalty": deg_penalty,
            "u": {"p_vals": p_vals_u, "q_vals": q_vals_u, "eps_nc": eps_u},
            "d": {"p_vals": p_vals_d, "q_vals": q_vals_d, "eps_nc": eps_d},
        },
        "u": {
            "choice": u.choice.__dict__,
            "masses": list(u.masses),
            "ratios": {"m1_over_m2": u.ratios[0], "m2_over_m3": u.ratios[1]},
        },
        "d": {
            "choice": d.choice.__dict__,
            "masses": list(d.masses),
            "ratios": {"m1_over_m2": d.ratios[0], "m2_over_m3": d.ratios[1]},
        },
        "CKM": {"angles": ang, "V_abs": np.abs(V).round(12).tolist()},
        "NEG": {"trivial_mix": {"angles": triv_ang, "V_abs": np.abs(V_triv).round(12).tolist()}},
        "cost": {"total": total, "u": u.cost, "d": d.cost},
    }


def run_enu(*, full: bool, top: int, seed: int, avoid_d_ratios: tuple[float, float] | None = None) -> dict:
    pis = list(perm_mats().keys())

    if full:
        c_vals = [-2, -1, 0, 1, 2]
        n_vals = [1, 2, 3, 4]
    else:
        c_vals = [-1, 0, 1]
        n_vals = [2, 3, 4]

    s_vals = [0, 1, 2]
    k_vals = [0, 1, 2]

    if full:
        q_vals_e = [1, 5]  # ±60°
        q_vals_n = [2, 4]  # ±120°
    else:
        q_vals_e = [5]
        q_vals_n = [4]

    p_vals_e = [1, 3, 5]
    p_vals_n = [2, 4, 6]

    # Discrete isospin sign on near-coupling contribution
    eps0 = 0.15
    eps_e = -eps0
    eps_n = +eps0

    E_cands = sector_scan(
        c_vals=c_vals,
        n_vals=n_vals,
        s_vals=s_vals,
        k_vals=k_vals,
        p_vals=p_vals_e,
        q_vals=q_vals_e,
        pi_names=pis,
        top=top,
        seed=seed,
        eps_nc=eps_e,
        prefer_strong_hierarchy=True,
    )

    N_cands = sector_scan(
        c_vals=c_vals,
        n_vals=n_vals,
        s_vals=s_vals,
        k_vals=k_vals,
        p_vals=p_vals_n,
        q_vals=q_vals_n,
        pi_names=pis,
        top=top,
        seed=seed + 1,
        eps_nc=eps_n,
        prefer_strong_hierarchy=False,
    )

    MR = np.diag([1.0, 2.0, 3.0]).astype(np.complex128)
    MR_inv = np.linalg.inv(MR)

    best_total: Optional[float] = None
    best_payload = None
    deg_penalty = 25.0  # fixed gate penalty

    for e in E_cands:
        # v0.7 gate: avoid mirroring chosen d-spectrum (if provided)
        e_pen = 0.0
        if avoid_d_ratios is not None and _ratios_too_close(e.ratios[0], e.ratios[1], avoid_d_ratios[0], avoid_d_ratios[1]):
            e_pen = deg_penalty

        for nd in N_cands:
            M_D = build_M(nd.choice, eps_nc=eps_n)
            M_nu = M_D.T @ MR_inv @ M_D
            m_nu, U_nu = diagonalize_yukawa(M_nu)

            mix_cost, U_pmns, ang = pair_cost_pmns(e.U, U_nu)
            total = e.cost + nd.cost + 0.5 * mix_cost + e_pen

            if best_total is None or total < best_total:
                best_total = total
                best_payload = (e, nd, m_nu, U_nu, U_pmns, ang, total, e_pen)

    assert best_payload is not None
    e, nd, m_nu, U_nu, U_pmns, ang, total, e_pen = best_payload

    U_triv = e.U.conjugate().T @ e.U
    triv_ang = extract_angles(U_triv)

    return {
        "version": "v0.9",
        "scan": {
            "full": full,
            "top": top,
            "seed": seed,
            "tiebreak": "cost_then_choice_lex_v0_1",
            "eps0": eps0,
            "MR_diag": [1, 2, 3],
            "deg_gate_rel": 1e-3,
            "deg_gate_penalty": deg_penalty,
            "avoid_d_ratios": list(avoid_d_ratios) if avoid_d_ratios is not None else None,
            "e_penalty_applied": float(e_pen),
            "e": {"p_vals": p_vals_e, "q_vals": q_vals_e, "eps_nc": eps_e},
            "nu_dirac": {"p_vals": p_vals_n, "q_vals": q_vals_n, "eps_nc": eps_n},
        },
        "e": {
            "choice": e.choice.__dict__,
            "masses": list(e.masses),
            "ratios": {"m1_over_m2": e.ratios[0], "m2_over_m3": e.ratios[1]},
        },
        "nu": {
            "choice_dirac": nd.choice.__dict__,
            "masses_proxy": [float(m_nu[0]), float(m_nu[1]), float(m_nu[2])],
            "ratios": {
                "m1_over_m2": float(m_nu[0] / m_nu[1]) if m_nu[1] > 0 else 0.0,
                "m2_over_m3": float(m_nu[1] / m_nu[2]) if m_nu[2] > 0 else 0.0,
            },
        },
        "PMNS": {"angles": ang, "U_abs": np.abs(U_pmns).round(12).tolist()},
        "NEG": {"trivial_mix": {"angles": triv_ang, "U_abs": np.abs(U_triv).round(12).tolist()}},
        "cost": {"total": total, "e": e.cost, "nu_dirac": nd.cost},
    }


def make_summary(ud: dict, enu: dict) -> str:
    def fmt_angles(tag: str, d: dict) -> str:
        a = d["angles"]
        return (
            f"{tag}: θ12={a['theta12_deg']:.6f}°, θ23={a['theta23_deg']:.6f}°, "
            f"θ13={a['theta13_deg']:.6f}°, J={a['J']:.6e}, δ(sin)={a['delta_deg_from_sin']:.6f}°"
        )

    lines: List[str] = []
    lines.append("# FLAVOR_LOCK summary (v0.9)")
    lines.append("")
    lines.append("Deterministiska, dimensionslösa kandidater. Inga SI-tal.")
    lines.append("")
    lines.append("## u/d")
    lines.append("")
    lines.append(
        f"u ratios: m1/m2={ud['u']['ratios']['m1_over_m2']:.6e}, m2/m3={ud['u']['ratios']['m2_over_m3']:.6e}"
    )
    lines.append(
        f"d ratios: m1/m2={ud['d']['ratios']['m1_over_m2']:.6e}, m2/m3={ud['d']['ratios']['m2_over_m3']:.6e}"
    )
    lines.append(fmt_angles("CKM", ud["CKM"]))
    lines.append("")
    lines.append("NEG(trivial): " + fmt_angles("CKM", ud["NEG"]["trivial_mix"]))
    lines.append("")
    lines.append("## e/ν")
    lines.append("")
    lines.append(
        f"e ratios: m1/m2={enu['e']['ratios']['m1_over_m2']:.6e}, m2/m3={enu['e']['ratios']['m2_over_m3']:.6e}"
    )
    lines.append(
        f"ν ratios(proxy): m1/m2={enu['nu']['ratios']['m1_over_m2']:.6e}, m2/m3={enu['nu']['ratios']['m2_over_m3']:.6e}"
    )
    lines.append(fmt_angles("PMNS", enu["PMNS"]))
    lines.append("")
    lines.append("NEG(trivial): " + fmt_angles("PMNS", enu["NEG"]["trivial_mix"]))
    lines.append("")
    lines.append("## Körning")
    lines.append("")
    lines.append("```bash")
    lines.append("python3 -u 00_TOP/LOCKS/FLAVOR_LOCK/flavor_lock_run.py")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="larger scan (slower)")
    ap.add_argument("--top", type=int, default=32, help="keep top-N per sector before pairing")
    ap.add_argument("--seed", type=int, default=1337, help="deterministic tie-break seed")
    args = ap.parse_args()

    repo = repo_root_from_here(Path(__file__))
    outA = repo / "out" / "FLAVOR_LOCK"
    outB = repo / "02_V7_ATOM" / "out" / "FLAVOR_LOCK"

    ensure_dir(outA)
    if (repo / "02_V7_ATOM").exists():
        ensure_dir(outB)

    ud = run_ud(full=args.full, top=args.top, seed=args.seed)
    enu = run_enu(full=args.full, top=args.top, seed=args.seed, avoid_d_ratios=(ud['d']['ratios']['m1_over_m2'], ud['d']['ratios']['m2_over_m3']))
    summary = make_summary(ud, enu)

    for outdir in [outA, outB] if outB.exists() else [outA]:
        write_json(outdir / "flavor_ud_v0_9.json", ud)
        write_json(outdir / "flavor_enu_v0_9.json", enu)
        write_text(outdir / "flavor_lock_summary_v0_9.md", summary)

    print(f"WROTE: {outA}")
    if outB.exists():
        print(f"WROTE: {outB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
