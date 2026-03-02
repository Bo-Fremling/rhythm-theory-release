#!/usr/bin/env python3
"""GS_LOCK coregen (NO-FACIT, Core-first).

Purpose
- Provide a SI-free Core boundary for the strong coupling sector.
- In Core we do NOT claim a unique numeric value for g_s(\mu). Instead we
  generate a finite candidate set for a dimensionless coupling proxy:

    alpha_s_RT := g_s^2 / (4*pi)

  built only from Core integers (L*=1260, cap=7, C30/divisors) + math constants.

Policy
- Must write only to out/CORE_GS_LOCK/
- Must NOT read Overlay/**
- Must NOT read any *reference*.json
- Must NOT score against PDG/CODATA/targets

Notes
- This is a candidate generator, not a fit. Selection (if any) must be via
  Core-only degeneracy-breaking locks later.
"""

from __future__ import annotations

import json
from datetime import datetime
from math import pi, sqrt
from pathlib import Path
from typing import Optional

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
    """Internal, facit-free complexity ordering: lower is preferred.

    Order: (token_count, has_pi, digit_count, expr_len)
    """
    has_pi = 1 if ("pi" in expr or "π" in expr) else 0
    token_count = sum(1 for ch in expr if ch in "+-*/") + 1
    digit_count = sum(1 for ch in expr if ch.isdigit())
    return (token_count, has_pi, digit_count, len(expr))


def _build_candidates() -> list[dict]:
    cand: list[dict] = []

    div42 = _divisors(42)

    # Family A: rational k/L*
    for k in div42:
        cand.append({"family": "A_rational_k_over_Lstar", "expr": f"{k}/{LSTAR}"})

    # Family B: 2*pi*k/L*
    for k in div42:
        cand.append({"family": "B_2pi_k_over_Lstar", "expr": f"2*pi*{k}/{LSTAR}"})

    # Family C: 1/d for C30-derived denominators
    denoms = sorted({30, 42, 60, 90, 126, 180, 210, 252, 315, 360, 420, 630, 840, 1260})
    for d in denoms:
        cand.append({"family": "C_unit_over_d", "expr": f"1/{d}"})

    # Family D: cap-shifted closure
    cand.append({"family": "D_cap_shift", "expr": f"1/{LSTAR - LCAP}"})
    cand.append({"family": "D_cap_shift", "expr": f"1/{LSTAR + LCAP}"})

    for i, c in enumerate(cand):
        c["complexity"] = list(_complexity(c["expr"]))
        c["id"] = f"AS{i:03d}"

    cand.sort(key=lambda x: tuple(x["complexity"]) + (x["family"], x["expr"]))
    return cand


def _filter_canon_denoms(cands: list[dict]) -> list[dict]:
    """Core-only reduction: keep only simple C30 denominators.

    Rationale (Core): candidates that align with the C30 strobe and the L*=1260
    closure admit a small set of canonical denominators. This is a degeneracy
    reduction, not a fit.
    """
    keep = {f"1/{d}" for d in CANON_DENOMS}
    out = [c for c in cands if isinstance(c, dict) and c.get('family') == 'C_unit_over_d' and c.get('expr') in keep]
    return out if out else cands


def _eval_expr(expr: str) -> Optional[float]:
    """Evaluate a tiny safe subset (rational + pi) for approx only.

    This is Core-safe: uses only integers and pi.
    """
    try:
        # NOTE: candidate expressions are generated internally and constrained.
        return float(eval(expr, {"__builtins__": {}}, {"pi": pi}))
    except Exception:
        return None


def _build_gs_candidates(alpha_s_cands: list[dict]) -> list[dict]:
    out: list[dict] = []
    for a in alpha_s_cands:
        aexpr = a.get("expr")
        if not isinstance(aexpr, str):
            continue
        # g_s := sqrt(4*pi*alpha_s) = 2*sqrt(pi*alpha_s)
        expr = f"2*sqrt(pi*({aexpr}))"
        aval = _eval_expr(aexpr)
        approx = None
        if aval is not None and aval >= 0:
            approx = float(2.0 * sqrt(pi * aval))
        out.append(
            {
                "id": f"GS_{a.get('id')}",
                "expr": expr,
                "approx": approx,
                "source_alpha_s_id": a.get("id"),
                "source_alpha_s_expr": aexpr,
                "complexity": list(_complexity(expr)),
            }
        )
    out.sort(key=lambda x: tuple(x.get("complexity") or [999, 999, 999, 999]) + (x.get("expr") or "",))
    return out


def main() -> int:
    out_dir = REPO / "out" / f"CORE_{LOCK}"
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates_full = _build_candidates()
    candidates = _filter_canon_denoms(candidates_full)
    gsc = _build_gs_candidates(candidates)

    preferred_alpha_s = candidates[0] if candidates else None
    preferred_gs = None
    if preferred_alpha_s is not None:
        pid = preferred_alpha_s.get("id")
        for g in gsc:
            if g.get("source_alpha_s_id") == pid:
                preferred_gs = {k: g.get(k) for k in ["id", "expr", "approx", "source_alpha_s_id", "source_alpha_s_expr"]}
                break

    out = {
        "version": "v0.3",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "lock": LOCK,
        "derivation_status": "CANDIDATE-SET",
        "validation_status": "UNTESTED",
        "core_definition": {
            "alpha_s_RT": {
                "type": "symbolic_constant",
                "unit": "dimensionless",
                "definition": "alpha_s_RT := g_s^2/(4*pi) (Core proxy; no numeric fixing yet).",
            },
            "g_s": {
                "type": "derived_symbol",
                "unit": "dimensionless",
                "definition": "g_s := sqrt(4*pi*alpha_s_RT) (formal; candidate-set if alpha_s_RT is candidate-set).",
            },
        },
        "candidate_space": {
            "alpha_s_RT": {
                "type": "finite_candidate_set",
                "candidates": candidates,
                "preferred": {k: preferred_alpha_s.get(k) for k in ["id", "expr", "family", "complexity"]} if preferred_alpha_s else None,
                "note": "Generated from Core integers (L*=1260, cap=7, divisors(42), C30 denominators) + math constant pi; no facit used.",
            },
            "g_s": {
                "type": "finite_derived_candidate_set",
                "relation": "g_s := 2*sqrt(pi*alpha_s_RT)",
                "with": "alpha_s_RT candidates",
                "candidates": gsc,
                "preferred": preferred_gs,
                "note": "Derived deterministically from alpha_s_RT candidates; approx uses only pi and rationals.",
            },
        },
        "tie_break": {
            "rule": "Order candidates by internal complexity (token_count, has_pi, digit_count, expr_len), then (family, expr).",
            "selected": None,
            "preferred": {
                "alpha_s_RT": {k: preferred_alpha_s.get(k) for k in ["id", "expr", "family", "complexity"]} if preferred_alpha_s else None,
                "g_s": preferred_gs,
            },
            "note": "Preferred is Core-internal (min complexity) and does not discard other candidates.",
        },
        "notes": [
            "Core does not encode running with scale mu yet; this is a structural candidate generator only.",
            "Overlay may compare alpha_s_RT candidates to PDG after the fact.",
        ],
    }

    jp = out_dir / "gs_lock_core_v0_3.json"
    jp.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    mp = out_dir / "gs_lock_core_v0_3.md"
    mp.write_text(
        "\n".join(
            [
                "# GS_LOCK Core (v0.3)",
                "",
                "- Derivation-status: **CANDIDATE-SET**",
                "- Validation-status: **UNTESTED**",
                "",
                "## Core definition",
                "- alpha_s_RT := g_s^2/(4*pi)",
                "- g_s := sqrt(4*pi*alpha_s_RT)",
                "",
                "## Candidate space",
                f"- Finite candidate-set built from L*={LSTAR}, cap={LCAP}, divisors(42), and C30 denominators.",
                "- No facit selection.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    # Back-compat stub
    old = out_dir / "gs_lock_core_v0_1.json"
    if not old.exists():
        old.write_text(json.dumps({"version": "v0.1", "deprecated": True, "migrated_to": "v0.2"}, indent=2) + "\n", encoding="utf-8")

    print(f"WROTE: {jp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
