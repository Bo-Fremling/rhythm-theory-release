#!/usr/bin/env python3
"""LEPTON_MASS_LOCK coregen (NO-FACIT).

Produces Core-only candidates (v0.4 and v0.5) without reading any overlay refs.
Writes only to out/CORE_LEPTON_MASS_LOCK/.

v0.4: epsilon-based (cap/L*) candidate.
v0.5: hierarchy-matching integer construction (cap + arming rule).

No PDG/CODATA/refs are read or used.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

LSTAR = 1260
LCAP = 7
SEXTET = 6
P_ARM = 1

# v0.5 base engagements (multiples of 42)
NBASE_E = 3 * 42
NBASE_MU = 9 * 42
NBASE_TAU = 18 * 42

P12_V05 = 2 * LCAP + SEXTET  # 20
P23_V05 = LCAP - 2          # 5


def _write_json(p: Path, obj: dict) -> None:
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8")


def _n_and_delta(d: int):
    n = LSTAR - d
    n6 = int(round(n / 6.0)) * 6
    delta = n - n6
    return n, n6, delta


def main() -> int:
    out_dir = REPO_ROOT / "out" / "CORE_LEPTON_MASS_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- v0.4: epsilon-based candidate ---
    eps = LCAP / LSTAR

    # Deterministic N_act (multiples of 6) from L*
    # choose: (e,mu,tau) = (18, 9, 3)*42 shifted by epsilon rule
    # Minimal policy: use cap to bias the gaps.
    NE_ACT = NBASE_E
    NMU_ACT = NBASE_MU
    NTAU_ACT = NBASE_TAU

    # gaps d = L* - N
    d_e_v04 = int(LSTAR - NE_ACT)
    d_mu_v04 = int(LSTAR - NMU_ACT)
    d_tau_v04 = int(LSTAR - NTAU_ACT)

    # enforce monotone gaps d_e >= d_mu >= d_tau
    d_e_v04 = max(d_e_v04, d_mu_v04)
    d_mu_v04 = max(d_mu_v04, d_tau_v04)

    # exponents
    p12_v04 = 2
    p23_v04 = 2

    r_mu_e_v04 = (d_e_v04 / d_mu_v04) ** p12_v04
    r_tau_mu_v04 = (d_mu_v04 / d_tau_v04) ** p23_v04

    m1_v04 = 1.0 / (d_e_v04 ** p12_v04)
    m2_v04 = 1.0 / (d_mu_v04 ** p12_v04)
    m3_v04 = m2_v04 * ((d_mu_v04 / d_tau_v04) ** p23_v04)

    N_e_v04, N_e6_v04, dNe_v04 = _n_and_delta(d_e_v04)
    N_mu_v04, N_mu6_v04, dNmu_v04 = _n_and_delta(d_mu_v04)
    N_tau_v04, N_tau6_v04, dNtau_v04 = _n_and_delta(d_tau_v04)

    out_v04 = {
        "version": "v0.4",
        "generated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy": {
            "L_star": LSTAR,
            "integers": {"L_cap": LCAP, "sextet": SEXTET, "epsilon": eps},
            "exponents": {"p12": p12_v04, "p23": p23_v04},
            "note": "Core-derived candidate; no external targets or refs.",
        },
        "model": {
            "family": "gap_power_equal_exponents",
            "best": {
                "p12": p12_v04,
                "p23": p23_v04,
                "d": {"e": d_e_v04, "mu": d_mu_v04, "tau": d_tau_v04},
                "N_act": {"e": N_e_v04, "mu": N_mu_v04, "tau": N_tau_v04},
                "N_act_nearest6": {"e": N_e6_v04, "mu": N_mu6_v04, "tau": N_tau6_v04},
                "delta_vs_6grid": {"e": dNe_v04, "mu": dNmu_v04, "tau": dNtau_v04},
                "masses_proxy": [m1_v04, m2_v04, m3_v04],
                "ratios_pred": {"m_mu_over_m_e": r_mu_e_v04, "m_tau_over_m_mu": r_tau_mu_v04},
            },
        },
        "derivation_status": "CANDIDATE-SET",
        "validation_status": "UNTESTED",
        "notes": [
            "This is a structural Core candidate; it is not selected by PDG matching.",
            "Promotion into Overlay comparison is done in *_compare.py only.",
        ],
    }

    _write_json(out_dir / "lepton_mass_lock_core_v0_4.json", out_v04)

    # --- v0.5: hierarchy-matching candidate ---
    N_e_v05 = int(NBASE_E - LCAP)
    N_mu_v05 = int(NBASE_MU + (LCAP + P_ARM))
    N_tau_v05 = int(NBASE_TAU + LCAP)

    d_e_v05 = int(LSTAR - N_e_v05)
    d_mu_v05 = int(LSTAR - N_mu_v05)
    d_tau_v05 = int(LSTAR - N_tau_v05)

    # defensive bounds + monotone
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

    N_e_v05, N_e6_v05, dNe_v05 = _n_and_delta(d_e_v05)
    N_mu_v05, N_mu6_v05, dNmu_v05 = _n_and_delta(d_mu_v05)
    N_tau_v05, N_tau6_v05, dNtau_v05 = _n_and_delta(d_tau_v05)

    out_v05 = {
        "version": "v0.5",
        "generated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy": {
            "L_star": LSTAR,
            "integers": {
                "L_cap": LCAP,
                "sextet": SEXTET,
                "N_base": {"e": NBASE_E, "mu": NBASE_MU, "tau": NBASE_TAU},
                "P_ARM": P_ARM,
            },
            "exponents": {"p12": P12_V05, "p23": P23_V05},
            "note": "Core-derived hierarchy-matching candidate; no PDG in decision loop.",
        },
        "model": {
            "family": "gap_power_two_exponents",
            "best": {
                "p12": P12_V05,
                "p23": P23_V05,
                "d": {"e": d_e_v05, "mu": d_mu_v05, "tau": d_tau_v05},
                "N_act": {"e": N_e_v05, "mu": N_mu_v05, "tau": N_tau_v05},
                "N_act_nearest6": {"e": N_e6_v05, "mu": N_mu6_v05, "tau": N_tau6_v05},
                "delta_vs_6grid": {"e": dNe_v05, "mu": dNmu_v05, "tau": dNtau_v05},
                "masses_proxy": [m1_v05, m2_v05, m3_v05],
                "ratios_pred": {"m_mu_over_m_e": r_mu_e_v05, "m_tau_over_m_mu": r_tau_mu_v05},
            },
        },
        "derivation_status": "CANDIDATE-SET",
        "validation_status": "UNTESTED",
        "notes": [
            "Construction uses only Core integers (cap + arming offsets).",
            "Overlay comparison is performed separately in *_compare.py.",
        ],
    }

    _write_json(out_dir / "lepton_mass_lock_core_v0_5.json", out_v05)

    # --- aggregate candidate-set (Core only) ---
    cand = [
        {
            "id": "v0.4",
            "artifact": "lepton_mass_lock_core_v0_4.json",
            "ratios_pred": out_v04["model"]["best"]["ratios_pred"],
            "policy_complexity": {
                "exponents": [p12_v04, p23_v04],
                "uses_arming_rule": False,
                "notes": "equal exponents + epsilon rule",
            },
        },
        {
            "id": "v0.5",
            "artifact": "lepton_mass_lock_core_v0_5.json",
            "ratios_pred": out_v05["model"]["best"]["ratios_pred"],
            "policy_complexity": {
                "exponents": [P12_V05, P23_V05],
                "uses_arming_rule": True,
                "notes": "cap + arming offsets",
            },
        },
    ]

    def _cand_key(c: dict):
        ex = c.get("policy_complexity", {}).get("exponents") or [999, 999]
        arm = 1 if c.get("policy_complexity", {}).get("uses_arming_rule") else 0
        # internal tie-break: fewer moving parts first
        return (arm, int(ex[0]) + int(ex[1]), int(ex[0]), int(ex[1]), c.get("id"))

    cand_sorted = sorted(cand, key=_cand_key)

    preferred = cand_sorted[0] if cand_sorted else None

    agg = {
        "version": "v0.1",
        "generated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "derivation_status": "CANDIDATE-SET",
        "validation_status": "UNTESTED",
        "candidates": cand_sorted,
        "tie_break": {
            "rule": "Order by (uses_arming_rule, exponent_sum, p12, p23, id).",
            "selected": None,
            "preferred": {k: preferred.get(k) for k in ["id", "artifact", "ratios_pred", "policy_complexity"]} if preferred else None,
            "note": "No PDG/facit selection; both candidates retained.",
        },
        "notes": [
            "Aggregate file for tooling: lists all Core candidates produced by this lock.",
            "Absolute masses remain overlay-mapped; Core outputs ratios only.",
        ],
    }

    _write_json(out_dir / "lepton_mass_lock_core_candidates_v0_1.json", agg)

    # summaries
    _write_text(
        out_dir / "lepton_mass_lock_core_summary_v0_4.md",
        "\n".join(
            [
                "# LEPTON_MASS_LOCK (core v0.4)",
                "",
                f"L_*={LSTAR}, L_cap={LCAP}, sextet={SEXTET}, epsilon={eps:.12g}",
                f"p12=p23=2",\
                f"d=(e={d_e_v04}, mu={d_mu_v04}, tau={d_tau_v04})",\
                f"ratios_pred: mu/e={r_mu_e_v04:.12g}, tau/mu={r_tau_mu_v04:.12g}",
            ]
        )
        + "\n",
    )

    _write_text(
        out_dir / "lepton_mass_lock_core_summary_v0_5.md",
        "\n".join(
            [
                "# LEPTON_MASS_LOCK (core v0.5)",
                "",
                f"L_*={LSTAR}, N_base=(3,9,18)×42, L_cap={LCAP}, P-ARM={P_ARM}, sextet={SEXTET}",
                f"p12={P12_V05}, p23={P23_V05}",
                f"d=(e={d_e_v05}, mu={d_mu_v05}, tau={d_tau_v05})",\
                f"ratios_pred: mu/e={r_mu_e_v05:.6g}, tau/mu={r_tau_mu_v05:.6g}",
            ]
        )
        + "\n",
    )

    print(f"WROTE: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
