#!/usr/bin/env python3
"""HIGGS_VEV_LOCK coregen (NO-FACIT, Core-first).

Purpose
- Provide a SI-free Core boundary for the minimal Higgs sector.
- v0.2 upgrades from a purely symbolic placeholder (HYP) to a *finite candidate-set*
  for a dimensionless VEV proxy (v_hat) and for the quartic coupling (lambda_H),
  generated only from Core integers (L*=1260, cap=7, C30/divisors) and simple
  rationals.
- v0.3 adds an explicit finite candidate-set for a Higgs-mass proxy mH_hat
  (dimensionless), built purely from (v_hat, lambda_H) candidates with an
  internal complexity ordering (no facit selection).

Core definitions
- v_RT is a tick^-1 scale in Core. Since Tick is a Core carrier (symbolic), we
  represent the VEV scale as:

    v_RT := v_hat / Tick

  where v_hat is dimensionless and admits a finite candidate-set.

Policy
- Must write only to out/CORE_HIGGS_VEV_LOCK/
- Must not read overlay-folder/** or any *reference*.json
- Must not score against PDG/CODATA/targets

Notes
- This does NOT claim a unique value for v_RT or mH_RT.
- mH_RT remains a derived symbol: mH_RT := sqrt(2*lambda_H) * v_RT.
- mH_hat is a dimensionless proxy: mH_hat := sqrt(2*lambda_H) * v_hat.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LOCK = Path(__file__).resolve().parent.name

LSTAR = 1260


def _cap_mag() -> int:
    """Preferred: read |L_cap| from CORE_GLOBAL_FRAME_CAP_LOCK artifact."""
    jp = REPO / "out" / "CORE_GLOBAL_FRAME_CAP_LOCK" / "global_frame_cap_lock_core_v0_1.json"
    if jp.exists():
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
            cap = data.get("cap") or {}
            return int(cap.get("L_cap_mag"))
        except Exception:
            pass
    return int(6 + 1)


LCAP = _cap_mag()

CANON_DENOMS = [30, 42, 60, 90]


def _divisors(n: int) -> list[int]:
    out: list[int] = []
    for k in range(1, n + 1):
        if n % k == 0:
            out.append(k)
    return out


def _complexity(expr: str) -> tuple[int, int, int, int]:
    has_pi = 1 if ("pi" in expr or "π" in expr) else 0
    token_count = sum(1 for ch in expr if ch in "+-*/") + 1
    digit_count = sum(1 for ch in expr if ch.isdigit())
    return (token_count, has_pi, digit_count, len(expr))


def _build_vhat_candidates() -> list[dict]:
    """Finite candidate-set for v_hat (dimensionless).

    IMPORTANT: placeholder generator. No facit, no selection.
    """
    cand: list[dict] = []
    div42 = _divisors(42)

    # Family A: k/L*
    for k in div42:
        cand.append({"family": "A_rational_k_over_Lstar", "expr": f"{k}/{LSTAR}"})

    # Family B: 2*pi*k/L*
    for k in div42:
        cand.append({"family": "B_2pi_k_over_Lstar", "expr": f"2*pi*{k}/{LSTAR}"})

    # Family C: 1/d
    denoms = sorted({30, 42, 60, 90, 126, 180, 210, 252, 315, 360, 420, 630, 840, 1260})
    for d in denoms:
        cand.append({"family": "C_unit_over_d", "expr": f"1/{d}"})

    # Family D: cap-shift
    cand.append({"family": "D_cap_shift", "expr": f"1/{LSTAR - LCAP}"})
    cand.append({"family": "D_cap_shift", "expr": f"1/{LSTAR + LCAP}"})

    for i, c in enumerate(cand):
        c["complexity"] = list(_complexity(c["expr"]))
        c["id"] = f"V{i:03d}"

    cand.sort(key=lambda x: tuple(x["complexity"]) + (x["family"], x["expr"]))

    # Core-only reduction: keep canonical C30 denominators for v_hat
    keep = {f"1/{d}" for d in CANON_DENOMS}
    reduced = [c for c in cand if c.get("family") == "C_unit_over_d" and c.get("expr") in keep]
    return reduced if reduced else cand


def _build_vhat_candidates_full() -> list[dict]:
    """Full (unreduced) candidate-set for v_hat (dimensionless).

    Used for transparency/debug; downstream selection should use the reduced set.
    """
    """Finite candidate-set for v_hat (dimensionless).

    IMPORTANT: placeholder generator. No facit, no selection.
    """
    cand: list[dict] = []
    div42 = _divisors(42)

    # Family A: k/L*
    for k in div42:
        cand.append({"family": "A_rational_k_over_Lstar", "expr": f"{k}/{LSTAR}"})

    # Family B: 2*pi*k/L*
    for k in div42:
        cand.append({"family": "B_2pi_k_over_Lstar", "expr": f"2*pi*{k}/{LSTAR}"})

    # Family C: 1/d
    denoms = sorted({30, 42, 60, 90, 126, 180, 210, 252, 315, 360, 420, 630, 840, 1260})
    for d in denoms:
        cand.append({"family": "C_unit_over_d", "expr": f"1/{d}"})

    # Family D: cap-shift
    cand.append({"family": "D_cap_shift", "expr": f"1/{LSTAR - LCAP}"})
    cand.append({"family": "D_cap_shift", "expr": f"1/{LSTAR + LCAP}"})

    for i, c in enumerate(cand):
        c["complexity"] = list(_complexity(c["expr"]))
        c["id"] = f"V{i:03d}"

    cand.sort(key=lambda x: tuple(x["complexity"]) + (x["family"], x["expr"]))
    return cand


def _build_lambda_candidates() -> list[dict]:
    # Small rational candidate-set (dimensionless), ordered by simple complexity.
    exprs = ["1/16", "1/8", "1/4", "1/2", "1", "2"]
    cand = []
    for i, e in enumerate(exprs):
        cand.append({"id": f"L{i:02d}", "expr": e, "complexity": list(_complexity(e))})
    cand.sort(key=lambda x: tuple(x["complexity"]) + (x["expr"],))
    return cand


def _build_mHhat_candidates(
    vhat: list[dict],
    lamb: list[dict],
    *,
    top_n: int = 64,
    max_v: int = 32,
) -> list[dict]:
    """Finite candidate-set for mH_hat (dimensionless).

    mH_hat := sqrt(2*lambda_H) * v_hat

    Policy
    - Use only Core-generated candidates (v_hat, lambda_H)
    - No score-to-facit
    - Deterministic internal ordering by complexity

    Implementation
    - Combine first `max_v` (lowest-complexity) v_hat candidates with all lambda_H
      candidates, rank by expression complexity, and keep top `top_n`.
    """
    combos: list[dict] = []
    v_subset = vhat[: max(1, int(max_v))]
    for v in v_subset:
        vexpr = v["expr"]
        vid = v.get("id")
        for lam in lamb:
            lexpr = lam["expr"]
            lid = lam.get("id")
            expr = f"sqrt(2*({lexpr}))*({vexpr})"
            combos.append(
                {
                    "family": "mH_hat_sqrt2lambda_times_vhat",
                    "expr": expr,
                    "parents": {"v_hat": vid, "lambda_H": lid},
                }
            )

    for i, c in enumerate(combos):
        c["complexity"] = list(_complexity(c["expr"]))
        c["id"] = f"MH{i:04d}"

    combos.sort(key=lambda x: tuple(x["complexity"]) + (x["expr"],))
    return combos[: max(1, int(top_n))]


def main() -> int:
    out_dir = REPO / "out" / f"CORE_{LOCK}"
    out_dir.mkdir(parents=True, exist_ok=True)

    vhat_full = _build_vhat_candidates_full()
    vhat = _build_vhat_candidates()
    lamb = _build_lambda_candidates()
    mhat = _build_mHhat_candidates(vhat, lamb, top_n=64, max_v=32)

    preferred = {
        "v_hat": {k: vhat[0].get(k) for k in ["id", "expr", "family", "complexity"]} if vhat else None,
        "lambda_H": {k: lamb[0].get(k) for k in ["id", "expr", "complexity"]} if lamb else None,
        "mH_hat": {k: mhat[0].get(k) for k in ["id", "expr", "parents", "complexity"]} if mhat else None,
    }

    out = {
        "version": "v0.5",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "lock": LOCK,
        "derivation_status": "CANDIDATE-SET",
        "validation_status": "UNTESTED",
        "core_definition": {
            "Tick": {
                "type": "carrier_symbol",
                "unit": "tick (symbolic)",
                "definition": "Core carrier; do not substitute legacy numeric Bf/Tick values.",
            },
            "v_hat": {
                "type": "dimensionless_proxy",
                "unit": "dimensionless",
                "definition": "Dimensionless VEV proxy used to express v_RT without SI.",
            },
            "v_RT": {
                "type": "derived_symbol",
                "unit": "tick^-1 (RT units)",
                "definition": "v_RT := v_hat / Tick.",
            },
            "lambda_H": {
                "type": "symbolic_constant",
                "unit": "dimensionless",
                "definition": "Higgs quartic coupling (dimensionless).",
            },
            "mH_RT": {
                "type": "derived_symbol",
                "unit": "tick^-1 (RT units)",
                "definition": "mH_RT := sqrt(2*lambda_H) * v_RT (tree-level minimal Higgs).",
            },
            "mH_hat": {
                "type": "dimensionless_proxy",
                "unit": "dimensionless",
                "definition": "mH_hat := sqrt(2*lambda_H) * v_hat (dimensionless Higgs-mass proxy).",
            },
        },
        "candidate_space": {
            "v_hat": {
                "type": "finite_candidate_set",
                "candidates": vhat,
                "preferred": preferred["v_hat"],
                "note": "Placeholder candidate generator from Core integers (L*, cap, C30). No facit selection.",
            },
            "lambda_H": {
                "type": "finite_candidate_set",
                "candidates": lamb,
                "preferred": preferred["lambda_H"],
                "note": "Small rational set; placeholder until a Core-only derivation exists.",
            },
            "mH_hat": {
                "type": "finite_candidate_set",
                "candidates": mhat,
                "preferred": preferred["mH_hat"],
                "note": "Derived candidate-set from (v_hat, lambda_H) with internal complexity ordering; no facit selection.",
            },
        },
        "tie_break": {
            "rule": "Order each candidate list by internal complexity; preferred is the first element in each list (min complexity).",
            "selected": None,
            "preferred": preferred,
        },
        "constraints": [
            "No SI numbers inside Core.",
            "No numeric legacy Bf usage inside Core.",
            "No score-to-facit in candidate generation or ordering.",
        ],
        "notes": [
            "This promotes Higgs VEV from purely symbolic (HYP) to a finite candidate space (CANDIDATE-SET).",
            "Physical degeneracy-breaking for v_hat/lambda_H is not implemented yet.",
        ],
    }

    jp = out_dir / "higgs_vev_lock_core_v0_5.json"
    jp.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    mp = out_dir / "higgs_vev_lock_core_v0_5.md"
    mp.write_text(
        "\n".join(
            [
                "# HIGGS_VEV_LOCK Core (v0.5)",
                "",
                "- Derivation-status: **CANDIDATE-SET**",
                "- Validation-status: **UNTESTED**",
                "",
                "## Core definition",
                "- v_RT := v_hat / Tick  (Tick är symbolisk i Core)",
                "- mH_RT := sqrt(2*lambda_H) * v_RT",
                "",
                "## Candidate space",
                f"- v_hat: finita uttryck från L*={LSTAR}, cap={LCAP}, C30.",
                "- lambda_H: liten rationell mängd.",
                "- mH_hat: kombinerad finita mängd (topp-N efter komplexitet).",
                "",
                "(Ingen facit-selektion.)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    # Keep old v0.1 file for backward compatibility if present.
    old = out_dir / "higgs_vev_lock_core_v0_1.json"
    if not old.exists():
        old.write_text(json.dumps({"version": "v0.1", "deprecated": True, "migrated_to": "v0.4"}, indent=2) + "\n", encoding="utf-8")

    print(f"WROTE: {jp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
