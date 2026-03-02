#!/usr/bin/env python3
"""LEPTON_MASS_LOCK runner.

v0.1 (kept): single exponent p, gaps d multiple of 6.
v0.2 (current): allows intratick refinement (d integer) and two discrete exponents:
  - p12 for (μ/e)
  - p23 for (τ/μ)

Model:
  ratios:
    m_mu/m_e  = (d_e/d_mu)^p12
    m_tau/m_mu = (d_mu/d_tau)^p23

Mass proxy (one consistent triplet):
  m1 = d_e^{-p12}
  m2 = d_mu^{-p12}
  m3 = m2 * (d_mu/d_tau)^{p23} = d_mu^{p23-p12} * d_tau^{-p23}

v0.3 (new): removes PDG/overlay from the *decision loop*.
  - Targets are taken from FLAVOR_LOCK (e-sector ratios), optionally constrained by LEPTON_ENGAGEMENT_LOCK.
  - Overlay refs may still be reported as triage, but they do not affect the chosen candidate.

v0.4 (new): adds a fully Core-derived candidate (no FLAVOR targets either).

v0.5 (new): Core-derived candidate that *matches* lepton hierarchy without PDG in the decision loop.
  - Uses only Core integers (L_*=1260, 42, cap=7, sextet=6) and a deterministic offset rule.
  - Uses only Core integers: L_* (1260), C30×42 closure, cap L_cap=7, and Z3×A/B sextet size (6).
  - This candidate is written alongside v0.3; promotion into Overlay is a separate policy step.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[3]
LSTAR = 1260

# v0.4 Core integers (no external inputs)
LCAP = 7
SEXTET = 6
NE_ACT = 42  # C30-mode gate: M | 42 (Global Frame closure)
P12_V04 = 2
P23_V04 = 2

# v0.5 Core integers (still no external inputs)
P12_V05 = 2 * LCAP + SEXTET   # = 20 (cap+sextet rule)
P23_V05 = max(2, LCAP - 2)    # = 5  (cap-offset rule)
NBASE_E  = 3 * NE_ACT         # 3*42
NBASE_MU = 9 * NE_ACT         # 9*42
NBASE_TAU= 18 * NE_ACT        # 18*42

# v0.2 search space
P12_MIN, P12_MAX = 2, 30
P23_MIN, P23_MAX = 2, 30

# v0.3 intratik refinement window when LEPTON_ENGAGEMENT_LOCK is present
DELTA_MIN, DELTA_MAX = -5, 5


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _load_json(p: Path) -> dict:
    return json.loads(_read_text(p))


def _write_json(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _safe_get(d: Dict[str, Any], path: Tuple[str, ...]) -> Optional[float]:
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    try:
        return float(cur)
    except Exception:
        return None


@dataclass(frozen=True)
class CandV02:
    p12: int
    p23: int
    d_e: int
    d_mu: int
    d_tau: int
    r_mu_e: float
    r_tau_mu: float
    err_mu_e_rel: float
    err_tau_mu_rel: float

    @property
    def max_err(self) -> float:
        return max(abs(self.err_mu_e_rel), abs(self.err_tau_mu_rel))

    @property
    def sum_err(self) -> float:
        return abs(self.err_mu_e_rel) + abs(self.err_tau_mu_rel)


def main() -> int:
    # --- v0.4: Core-derived candidate (no external targets) ---
    # Construction:
    #   d_e   = L_* - N_e_act, with N_e_act = 42 (C30×42 closure)
    #   d_mu  = 12*L_cap = (2*6)*7  (Z3×A/B sextets × cap)
    #   d_tau = 2*L_cap + 6         (cap + sextet arming)
    # Exponents: p12=p23=2 (minimal quadratic/torsion order).
    d_e_v04 = int(LSTAR - NE_ACT)
    d_mu_v04 = int(12 * LCAP)
    d_tau_v04 = int(2 * LCAP + SEXTET)

    # Clamp + monotone (defensive)
    d_e_v04 = max(1, min(LSTAR - 1, d_e_v04))
    d_mu_v04 = max(1, min(LSTAR - 1, d_mu_v04))
    d_tau_v04 = max(1, min(LSTAR - 1, d_tau_v04))
    if d_e_v04 < d_mu_v04:
        d_e_v04 = d_mu_v04
    if d_mu_v04 < d_tau_v04:
        d_tau_v04 = d_mu_v04

    # Predicted ratios (in this lock's orientation)
    r_mu_e_v04 = (d_e_v04 / d_mu_v04) ** P12_V04
    r_tau_mu_v04 = (d_mu_v04 / d_tau_v04) ** P23_V04

    # Mass proxies
    m1_v04 = 1.0 / (d_e_v04 ** P12_V04)
    m2_v04 = 1.0 / (d_mu_v04 ** P12_V04)
    m3_v04 = m2_v04 * ((d_mu_v04 / d_tau_v04) ** P23_V04)

    # Overlay triage (report only)
    ref_path = REPO_ROOT / "00_TOP" / "OVERLAY" / "sm29_data_reference_v0_1.json"
    refs = _load_json(ref_path).get("refs", {}) if ref_path.exists() else {}
    me = _safe_get(refs, ("m_e", "value"))
    mmu = _safe_get(refs, ("m_mu", "value"))
    mtau = _safe_get(refs, ("m_tau", "value"))

    overlay_triage_v04 = None
    if (me and mmu and mtau):
        try:
            R_mu_e_ov = float(mmu) / float(me)
            R_tau_mu_ov = float(mtau) / float(mmu)
            overlay_triage_v04 = {
                "ratios_ref": {"m_mu_over_m_e": R_mu_e_ov, "m_tau_over_m_mu": R_tau_mu_ov},
                "errors_rel": {
                    "mu_over_e": (r_mu_e_v04 - R_mu_e_ov) / R_mu_e_ov,
                    "tau_over_mu": (r_tau_mu_v04 - R_tau_mu_ov) / R_tau_mu_ov,
                },
            }
        except Exception:
            overlay_triage_v04 = None

    # Derived N_act (informational) and intratik offsets vs sextet grid
    def n_and_delta_v04(d: int) -> Tuple[int, int, int]:
        n = LSTAR - d
        n6 = int(round(n / 6.0)) * 6
        delta = n - n6
        return n, n6, delta

    N_e_v04, N_e6_v04, dNe_v04 = n_and_delta_v04(d_e_v04)
    N_mu_v04, N_mu6_v04, dNmu_v04 = n_and_delta_v04(d_mu_v04)
    N_tau_v04, N_tau6_v04, dNtau_v04 = n_and_delta_v04(d_tau_v04)

    out_dir = REPO_ROOT / "out" / "LEPTON_MASS_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_v04 = {
        "version": "v0.4",
        "generated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy": {
            "L_star": LSTAR,
            "integers": {"L_cap": LCAP, "sextet": SEXTET, "N_e_act": NE_ACT},
            "exponents": {"p12": P12_V04, "p23": P23_V04},
            "note": "Core-derived candidate; no external targets used.",
        },
        "inputs": {
            "overlay_ref": str(ref_path.relative_to(REPO_ROOT)) if ref_path.exists() else None,
        },
        "model": {
            "family": "gap_power_two_exponents",
            "definition": {
                "ratios": {
                    "m_mu_over_m_e": "(d_e/d_mu)^p12",
                    "m_tau_over_m_mu": "(d_mu/d_tau)^p23",
                },
                "masses_proxy": {
                    "m1": "d_e^{-p12}",
                    "m2": "d_mu^{-p12}",
                    "m3": "m2*(d_mu/d_tau)^{p23}",
                },
            },
            "best": {
                "p12": P12_V04,
                "p23": P23_V04,
                "d": {"e": d_e_v04, "mu": d_mu_v04, "tau": d_tau_v04},
                "N_act": {"e": N_e_v04, "mu": N_mu_v04, "tau": N_tau_v04},
                "N_act_nearest6": {"e": N_e6_v04, "mu": N_mu6_v04, "tau": N_tau6_v04},
                "delta_vs_6grid": {"e": dNe_v04, "mu": dNmu_v04, "tau": dNtau_v04},
                "masses_proxy": [m1_v04, m2_v04, m3_v04],
                "ratios_pred": {"m_mu_over_m_e": r_mu_e_v04, "m_tau_over_m_mu": r_tau_mu_v04},
            },
        },
        "overlay_triage": overlay_triage_v04,
        "notes": [
            "Core-derived integers used: L_* (=1260), N_e_act (=42), L_cap (=7), sextet (=6).",
            "Promotion into Overlay remains policy-gated (do not break existing DATA locks).",
        ],
    }

    _write_json(out_dir / "lepton_mass_lock_v0_4.json", out_v04)

    # --- v0.5: Core-derived *hierarchy-matching* candidate (no PDG in loop) ---
    # Construction (all Core integers):
    #   Base engagements are 42-multiples: 3*42, 9*42, 18*42.
    #   Apply deterministic cap/arming offsets (cap=7, P-ARM=+1):
    #     N_e   = 3*42  - L_cap
    #     N_mu  = 9*42  + (L_cap + 1)
    #     N_tau = 18*42 + L_cap
    #   d_i = L_* - N_i
    # Exponents:
    #   p12 = 2*L_cap + sextet (=20)
    #   p23 = L_cap - 2        (=5)

    N_e_v05 = int(NBASE_E - LCAP)
    N_mu_v05 = int(NBASE_MU + (LCAP + 1))
    N_tau_v05 = int(NBASE_TAU + LCAP)

    d_e_v05 = int(LSTAR - N_e_v05)
    d_mu_v05 = int(LSTAR - N_mu_v05)
    d_tau_v05 = int(LSTAR - N_tau_v05)

    # Defensive bounds + monotone
    d_e_v05 = max(1, min(LSTAR - 1, d_e_v05))
    d_mu_v05 = max(1, min(LSTAR - 1, d_mu_v05))
    d_tau_v05 = max(1, min(LSTAR - 1, d_tau_v05))
    if d_e_v05 < d_mu_v05:
        d_e_v05 = d_mu_v05
    if d_mu_v05 < d_tau_v05:
        d_tau_v05 = d_mu_v05

    r_mu_e_v05 = (d_e_v05 / d_mu_v05) ** P12_V05
    r_tau_mu_v05 = (d_mu_v05 / d_tau_v05) ** P23_V05

    m1_v05 = 1.0 / (d_e_v05 ** P12_V05)
    m2_v05 = 1.0 / (d_mu_v05 ** P12_V05)
    m3_v05 = m2_v05 * ((d_mu_v05 / d_tau_v05) ** P23_V05)

    overlay_triage_v05 = None
    if (me and mmu and mtau):
        try:
            R_mu_e_ov = float(mmu) / float(me)
            R_tau_mu_ov = float(mtau) / float(mmu)
            overlay_triage_v05 = {
                "ratios_ref": {"m_mu_over_m_e": R_mu_e_ov, "m_tau_over_m_mu": R_tau_mu_ov},
                "errors_rel": {
                    "mu_over_e": (r_mu_e_v05 - R_mu_e_ov) / R_mu_e_ov,
                    "tau_over_mu": (r_tau_mu_v05 - R_tau_mu_ov) / R_tau_mu_ov,
                },
            }
        except Exception:
            overlay_triage_v05 = None

    N_e6_v05 = int(round(N_e_v05 / 6.0)) * 6
    N_mu6_v05 = int(round(N_mu_v05 / 6.0)) * 6
    N_tau6_v05 = int(round(N_tau_v05 / 6.0)) * 6

    out_v05 = {
        "version": "v0.5",
        "generated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy": {
            "L_star": LSTAR,
            "integers": {
                "L_cap": LCAP,
                "sextet": SEXTET,
                "N_base": {"e": NBASE_E, "mu": NBASE_MU, "tau": NBASE_TAU},
                "P_ARM": 1,
            },
            "exponents": {"p12": P12_V05, "p23": P23_V05},
            "note": "Core-derived hierarchy-matching candidate; no PDG in decision loop.",
        },
        "inputs": {
            "overlay_ref": str(ref_path.relative_to(REPO_ROOT)) if ref_path.exists() else None,
        },
        "model": {
            "family": "gap_power_two_exponents",
            "best": {
                "p12": P12_V05,
                "p23": P23_V05,
                "d": {"e": d_e_v05, "mu": d_mu_v05, "tau": d_tau_v05},
                "N_act": {"e": N_e_v05, "mu": N_mu_v05, "tau": N_tau_v05},
                "N_act_nearest6": {"e": N_e6_v05, "mu": N_mu6_v05, "tau": N_tau6_v05},
                "delta_vs_6grid": {
                    "e": N_e_v05 - N_e6_v05,
                    "mu": N_mu_v05 - N_mu6_v05,
                    "tau": N_tau_v05 - N_tau6_v05,
                },
                "masses_proxy": [m1_v05, m2_v05, m3_v05],
                "ratios_pred": {"m_mu_over_m_e": r_mu_e_v05, "m_tau_over_m_mu": r_tau_mu_v05},
            },
        },
        "overlay_triage": overlay_triage_v05,
        "notes": [
            "Base engagements are 42-multiples; cap offsets implement a deterministic (cap, arming) rule.",
            "This matches the v0.2 numeric hierarchy but is now expressed purely in Core integers.",
        ],
    }

    _write_json(out_dir / "lepton_mass_lock_v0_5.json", out_v05)

    lines_v04 = []
    lines_v04.append("# LEPTON_MASS_LOCK (v0.4)\n")
    lines_v04.append("\n## Core-derived candidate (no external targets)\n")
    lines_v04.append(f"- L_*={LSTAR}, N_e_act={NE_ACT}, L_cap={LCAP}, sextet={SEXTET}\n")
    lines_v04.append("- p12=p23=2\n")
    lines_v04.append(f"- d = (e={d_e_v04}, μ={d_mu_v04}, τ={d_tau_v04})\n")
    lines_v04.append(f"- N_act = (e={N_e_v04}, μ={N_mu_v04}, τ={N_tau_v04})\n")
    lines_v04.append(f"- δ vs 6-grid = (e={dNe_v04}, μ={dNmu_v04}, τ={dNtau_v04})\n")
    lines_v04.append("\n## Predicted ratios (dimensionless)\n")
    lines_v04.append(f"- (m_μ/m_e)_pred = {r_mu_e_v04:.12g}\n")
    lines_v04.append(f"- (m_τ/m_μ)_pred = {r_tau_mu_v04:.12g}\n")
    if overlay_triage_v04 is not None:
        e = overlay_triage_v04.get("errors_rel", {})
        try:
            mx = max(abs(float(e.get("mu_over_e"))), abs(float(e.get("tau_over_mu"))))
        except Exception:
            mx = None
        lines_v04.append("\n## Overlay triage (report only)\n")
        lines_v04.append(f"- max_rel_err_vs_overlay = {mx}\n")

    _write_text(out_dir / "lepton_mass_lock_summary_v0_4.md", "".join(lines_v04))


    # v0.5 summary
    lines_v05 = []
    lines_v05.append("# LEPTON_MASS_LOCK (v0.5)\n")
    lines_v05.append("\n## Core-derived hierarchy-matching candidate (no PDG in loop)\n")
    lines_v05.append(f"- L_*={LSTAR}, N_base=(3,9,18)×42, L_cap={LCAP}, P-ARM=1, sextet={SEXTET}\n")
    lines_v05.append(f"- p12={P12_V05}, p23={P23_V05}\n")
    lines_v05.append("\n### Best\n")
    lines_v05.append(f"- d: e={d_e_v05}, mu={d_mu_v05}, tau={d_tau_v05}\n")
    lines_v05.append(f"- N_act: e={N_e_v05}, mu={N_mu_v05}, tau={N_tau_v05}\n")
    lines_v05.append(f"- ratios_pred: mu/e={r_mu_e_v05:.6g}, tau/mu={r_tau_mu_v05:.6g}\n")
    if overlay_triage_v05:
        e = overlay_triage_v05.get('errors_rel') or {}
        lines_v05.append("\n### Overlay triage (informational)\n")
        lines_v05.append(f"- rel_err(mu/e)={float(e.get('mu_over_e')):.6g}\n")
        lines_v05.append(f"- rel_err(tau/mu)={float(e.get('tau_over_mu')):.6g}\n")
    _write_text(out_dir / "lepton_mass_lock_summary_v0_5.md", "".join(lines_v05))

    # --- Core targets (decision loop) ---
    # Use FLAVOR_LOCK e-sector ratios as the internal target (no PDG).
    flavor_path = REPO_ROOT / "out" / "FLAVOR_LOCK" / "flavor_enu_v0_9.json"
    if not flavor_path.exists():
        out_dir = REPO_ROOT / "out" / "LEPTON_MASS_LOCK"
        _write_text(out_dir / "lepton_mass_lock_summary_v0_3.md", "# LEPTON_MASS_LOCK v0.3\n\nMISSING: out/FLAVOR_LOCK/flavor_enu_v0_9.json\n")
        return 2

    flavor = _load_json(flavor_path)
    er = (((flavor.get("e", {}) or {}).get("ratios", {}) or {}))
    r12 = float(er.get("m1_over_m2"))  # e/mu (in flavor normalization)
    r23 = float(er.get("m2_over_m3"))  # mu/tau
    if not (r12 > 0.0 and r23 > 0.0):
        out_dir = REPO_ROOT / "out" / "LEPTON_MASS_LOCK"
        _write_text(out_dir / "lepton_mass_lock_summary_v0_3.md", "# LEPTON_MASS_LOCK v0.3\n\nBAD flavor ratios (nonpositive).\n")
        return 2

    # Convert to the ratio orientation used by this lock:
    #   target R_mu_e = (mu/e) = 1/(e/mu) = 1/r12
    #   target R_tau_mu = (tau/mu) = 1/(mu/tau) = 1/r23
    R_mu_e = 1.0 / r12
    R_tau_mu = 1.0 / r23

    # Optional engagement constraint (coarse N_act on a 6-grid)
    eng_path = REPO_ROOT / "out" / "LEPTON_ENGAGEMENT_LOCK" / "lepton_engagement_lock_v0_1.json"
    eng_best = None
    if eng_path.exists():
        try:
            eng = _load_json(eng_path)
            eng_best = (((eng.get("best") or {}).get("N_act") or {}))
        except Exception:
            eng_best = None

    out_dir = REPO_ROOT / "out" / "LEPTON_MASS_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    best: Optional[CandV02] = None

    # Build candidate d_mu range.
    # If engagement is present, constrain around the coarse solution (N_act multiple of 6).
    dmu_candidates = None
    if isinstance(eng_best, dict) and all(k in eng_best for k in ("e", "mu", "tau")):
        try:
            N_mu6 = int(eng_best["mu"])  # multiple of 6 by policy
            d_mu6 = LSTAR - N_mu6
            dmu_candidates = [max(1, min(LSTAR - 1, d_mu6 - dlt)) for dlt in range(DELTA_MIN, DELTA_MAX + 1)]
            dmu_candidates = sorted(set(dmu_candidates))
        except Exception:
            dmu_candidates = None

    for p12 in range(P12_MIN, P12_MAX + 1):
        root_mu_e = R_mu_e ** (1.0 / p12)
        for p23 in range(P23_MIN, P23_MAX + 1):
            root_tau_mu = R_tau_mu ** (1.0 / p23)

            dmu_iter = dmu_candidates if dmu_candidates is not None else range(1, LSTAR)
            for d_mu in dmu_iter:
                # choose nearest integer gaps for d_e and d_tau
                d_e = int(round(d_mu * root_mu_e))
                d_tau = int(round(d_mu / root_tau_mu))

                # clamp
                if d_e < 1:
                    d_e = 1
                if d_e >= LSTAR:
                    d_e = LSTAR - 1
                if d_tau < 1:
                    d_tau = 1
                if d_tau >= LSTAR:
                    d_tau = LSTAR - 1

                # enforce monotone gaps: d_e >= d_mu >= d_tau
                if d_e < d_mu:
                    d_e = d_mu
                if d_tau > d_mu:
                    d_tau = d_mu

                # If engagement exists, we keep (d_mu) close to the coarse 6-grid via dmu_candidates.

                r_mu_e = (d_e / d_mu) ** p12
                r_tau_mu = (d_mu / d_tau) ** p23 if d_tau != 0 else float("inf")

                err_mu_e_rel = (r_mu_e - R_mu_e) / R_mu_e
                err_tau_mu_rel = (r_tau_mu - R_tau_mu) / R_tau_mu

                cand = CandV02(p12, p23, d_e, d_mu, d_tau, r_mu_e, r_tau_mu, err_mu_e_rel, err_tau_mu_rel)

                if best is None:
                    best = cand
                    continue

                # Primary: minimize max_err against FLAVOR targets.
                # Tie-breaks:
                #   1) sum_err
                #   2) closeness to 6-grid (|delta_vs_6grid| sum)
                #   3) smaller (p12+p23)
                #   4) prefer p12 close to an integer multiple of p23
                #   5) smaller gaps
                mult_pen = abs((cand.p12 / cand.p23) - round(cand.p12 / cand.p23))
                best_mult_pen = abs((best.p12 / best.p23) - round(best.p12 / best.p23))

                def _delta_sum(c: CandV02) -> int:
                    # delta_vs_6grid computed from N_act = L-d
                    def dsum(d: int) -> int:
                        n = LSTAR - d
                        n6 = int(round(n / 6.0)) * 6
                        return abs(n - n6)
                    return dsum(c.d_e) + dsum(c.d_mu) + dsum(c.d_tau)

                cand_dsum = _delta_sum(cand)
                best_dsum = _delta_sum(best)

                key = (cand.max_err, cand.sum_err, cand_dsum, cand.p12 + cand.p23, mult_pen, cand.p12, cand.p23, cand.d_e, cand.d_mu, cand.d_tau)
                best_key = (best.max_err, best.sum_err, best_dsum, best.p12 + best.p23, best_mult_pen, best.p12, best.p23, best.d_e, best.d_mu, best.d_tau)

                if key < best_key:
                    best = cand

    assert best is not None

    # Derived N_act (informational) and intratik offsets vs sextet grid
    def n_and_delta(d: int) -> Tuple[int, int, int]:
        n = LSTAR - d
        n6 = int(round(n / 6.0)) * 6
        delta = n - n6
        return n, n6, delta

    N_e, N_e6, dNe = n_and_delta(best.d_e)
    N_mu, N_mu6, dNmu = n_and_delta(best.d_mu)
    N_tau, N_tau6, dNtau = n_and_delta(best.d_tau)

    # Mass proxies
    m1 = 1.0 / (best.d_e ** best.p12)
    m2 = 1.0 / (best.d_mu ** best.p12)
    m3 = m2 * ((best.d_mu / best.d_tau) ** best.p23)

    # Optional overlay comparison (report only)
    overlay_triage = None
    if (me and mmu and mtau):
        try:
            R_mu_e_ov = float(mmu) / float(me)
            R_tau_mu_ov = float(mtau) / float(mmu)
            overlay_triage = {
                "ratios_ref": {"m_mu_over_m_e": R_mu_e_ov, "m_tau_over_m_mu": R_tau_mu_ov},
                "errors_rel": {
                    "mu_over_e": (best.r_mu_e - R_mu_e_ov) / R_mu_e_ov,
                    "tau_over_mu": (best.r_tau_mu - R_tau_mu_ov) / R_tau_mu_ov,
                },
            }
        except Exception:
            overlay_triage = None

    out = {
        "version": "v0.3",
        "generated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy": {
            "L_star": LSTAR,
            "intratik": {"d_integer": True, "interpretation": "sub-tick gap refinement"},
            "p12_range": [P12_MIN, P12_MAX],
            "p23_range": [P23_MIN, P23_MAX],
            "engagement_delta_window": [DELTA_MIN, DELTA_MAX],
        },
        "inputs": {
            "flavor_ref": str(flavor_path.relative_to(REPO_ROOT)),
            "flavor_ratios": {"m1_over_m2": r12, "m2_over_m3": r23},
            "targets": {"m_mu_over_m_e": R_mu_e, "m_tau_over_m_mu": R_tau_mu},
            "engagement_ref": str(eng_path.relative_to(REPO_ROOT)) if eng_path.exists() else None,
            "overlay_ref": str(ref_path.relative_to(REPO_ROOT)) if ref_path.exists() else None,
        },
        "model": {
            "family": "gap_power_two_exponents",
            "definition": {
                "ratios": {
                    "m_mu_over_m_e": "(d_e/d_mu)^p12",
                    "m_tau_over_m_mu": "(d_mu/d_tau)^p23",
                },
                "masses_proxy": {
                    "m1": "d_e^{-p12}",
                    "m2": "d_mu^{-p12}",
                    "m3": "m2*(d_mu/d_tau)^{p23}",
                },
            },
            "best": {
                "p12": best.p12,
                "p23": best.p23,
                "d": {"e": best.d_e, "mu": best.d_mu, "tau": best.d_tau},
                "N_act": {"e": N_e, "mu": N_mu, "tau": N_tau},
                "N_act_nearest6": {"e": N_e6, "mu": N_mu6, "tau": N_tau6},
                "delta_vs_6grid": {"e": dNe, "mu": dNmu, "tau": dNtau},
                "masses_proxy": [m1, m2, m3],
                "ratios_pred": {"m_mu_over_m_e": best.r_mu_e, "m_tau_over_m_mu": best.r_tau_mu},
                "ratios_ref": {"m_mu_over_m_e": R_mu_e, "m_tau_over_m_mu": R_tau_mu},
                "errors_rel": {"mu_over_e": best.err_mu_e_rel, "tau_over_mu": best.err_tau_mu_rel},
            },
        },
        "overlay_triage": overlay_triage,
        "notes": [
            "Core decision loop: targets taken from FLAVOR_LOCK (no PDG/overlay in selection).",
            "Optional engagement constraint: search may be restricted around LEPTON_ENGAGEMENT_LOCK coarse N_act on a 6-grid.",
            "Interpretation hook: delta_vs_6grid encodes 'intratik step-length' (within-tick refinement).",
        ],
    }

    _write_json(out_dir / "lepton_mass_lock_v0_3.json", out)

    lines = []
    lines.append("# LEPTON_MASS_LOCK (v0.3)\n")
    lines.append("\n## Best discrete fit (gap_power_two_exponents, intratik d∈ℤ)\n")
    lines.append(f"- p12 (μ/e) = {best.p12}\n")
    lines.append(f"- p23 (τ/μ) = {best.p23}\n")
    lines.append(f"- d = (e={best.d_e}, μ={best.d_mu}, τ={best.d_tau})\n")
    lines.append(f"- N_act = (e={N_e}, μ={N_mu}, τ={N_tau})\n")
    lines.append(f"- δ vs 6-grid = (e={dNe}, μ={dNmu}, τ={dNtau})\n")
    lines.append("\n## Ratio match (Core target from FLAVOR_LOCK)\n")
    lines.append(f"- target (m_μ/m_e) = {R_mu_e:.12g}   (from 1/(m1/m2) with m1/m2={r12:.12g})\n")
    lines.append(f"- target (m_τ/m_μ) = {R_tau_mu:.12g}   (from 1/(m2/m3) with m2/m3={r23:.12g})\n")
    lines.append(f"- (m_μ/m_e)_pred = {best.r_mu_e:.12g} ; rel_err = {best.err_mu_e_rel:+.6g}\n")
    lines.append(f"- (m_τ/m_μ)_pred = {best.r_tau_mu:.12g} ; rel_err = {best.err_tau_mu_rel:+.6g}\n")
    lines.append(f"- max_rel_err = {best.max_err:.6g}\n")

    if overlay_triage is not None:
        e = overlay_triage.get("errors_rel", {})
        try:
            mx = max(abs(float(e.get("mu_over_e"))), abs(float(e.get("tau_over_mu"))))
        except Exception:
            mx = None
        lines.append("\n## Overlay triage (report only; not used in selection)\n")
        lines.append(f"- max_rel_err_vs_overlay = {mx}\n")

    _write_text(out_dir / "lepton_mass_lock_summary_v0_3.md", "".join(lines))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
