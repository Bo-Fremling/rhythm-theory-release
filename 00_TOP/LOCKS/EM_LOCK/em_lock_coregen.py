#!/usr/bin/env python3
"""EM_LOCK coregen (NO-FACIT, Core-first).

Purpose:
- Establish a SI-free *Core* definition boundary for the EM sector without importing
  any overlay refs / facit / facit.
- Output is SI-free and Core-internal.
- v0.2 adds a *candidate-set* for Xi_RT built only from Core integers
  (C30/L*/cap/divisors) plus math constants, with an internal complexity
  ordering. This is still not a unique derivation; it is a candidate space.

Policy:
- Must write only to out/CORE_EM_LOCK/
- Must not read overlay-folder/** or any *reference*.json

Notes:
- Bf is legacy/approx and must not be used numerically.
- Overlay may later map to SI (Z0/G0) for *comparison only*.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import math

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
    # Fallback: canonical Core rule (bias-nollning sextet 6 + P-ARM 1)
    return int(6 + 1)


LCAP = _cap_mag()
K_TICKS = 30
RHO = 10
MODE_MAX = 42  # since L* = 30*42


def _divisors(n: int) -> list[int]:
    out: list[int] = []
    for k in range(1, n + 1):
        if n % k == 0:
            out.append(k)
    return out


def _complexity(expr: str) -> tuple[int, int, int, int]:
    """Internal, facit-free complexity: lower is preferred.

    Order: (token_count, has_pi, digit_count, expr_len)
    """
    has_pi = 1 if "pi" in expr or "π" in expr else 0
    token_count = sum(1 for ch in expr if ch in "+-*/") + 1
    digit_count = sum(1 for ch in expr if ch.isdigit())
    return (token_count, has_pi, digit_count, len(expr))


def _build_candidates() -> list[dict]:
    """Build a small, deterministic candidate set for Xi_RT.

    IMPORTANT: This is NOT fit-to-data; it is purely generated from Core
    integers (C30/L*/cap) + math constants.
    """
    cand: list[dict] = []

    # Core integer families
    # - L* = 1260 = 30*42
    # - allow k in divisors(42) for mode-gated families
    div42 = _divisors(42)

    # Family A: Xi = k / L*  (pure rational)
    for k in div42:
        expr = f"{k}/{LSTAR}"
        cand.append({"family": "A_rational_k_over_Lstar", "expr": expr})

    # Family B: Xi = 2*pi*k / L*  (geometry-phase rational)
    # We keep pi symbolic in expr; complexity ordering is still internal.
    for k in div42:
        expr = f"2*pi*{k}/{LSTAR}"
        cand.append({"family": "B_2pi_k_over_Lstar", "expr": expr})

    # Family E: AB-edge corrected phase family (Core semantics)
    # Xi = 2*pi*(k*K - 2)/(K*L*)
    # Motivation: Xi_RT corresponds to the E+B window (two edges) over a C30 strobe;
    # we model this as a minimal 2-tick correction across K ticks.
    for k in div42:
        expr = f"2*pi*({k}*{K_TICKS}-2)/({K_TICKS}*{LSTAR})"
        cand.append({"family": "E_2pi_abcorr_over_Lstar", "expr": expr})

    # Family F: AB-edge + rho/mode micro-correction (Core-only, no facit)
    # Xi = 2*pi*(k*K - (2 + 2/rho - 1/(rho*(42-k))))/(K*L*)
    # Motivation:
    # - '2' = two-edge window (E+B) on the C30 strobe
    # - 2/rho = ten-per-tick (rho=10) micro-extrema contribution
    # - 1/(rho*(42-k)) = mode-gate correction tied to the global-frame factor 42 and selected mode k
    # This is still a candidate family; selection is done only by Core semantic gates.
    for k in div42:
        if k >= MODE_MAX:
            continue  # avoid 42-k = 0
        expr = (
            f"2*pi*({k}*{K_TICKS}-(2+2/{RHO}-1/({RHO}*(42-{k}))))"
            f"/({K_TICKS}*{LSTAR})"
        )
        cand.append({"family": "F_2pi_abcorr_rho_modecorr", "expr": expr})

    # Family G: add cap-arming correction (Core-only, no facit)
    # Xi = 2*pi*(k*K-(2+2/rho-1/(rho*(42-k)) - 1/(rho*(42-k)*K*L_cap)))/(K*L*)
    # Motivation:
    # - L_cap=7 is the global-frame cap derived in Core (bias-nollning + P-ARM),
    #   and should imprint as a tiny edge-correction weight over the AB window.
    # - Model this as an additional correction scaling with (K*L_cap) on top of
    #   the rho/mode gate.
    for k in div42:
        if k >= MODE_MAX:
            continue
        expr = (
            f"2*pi*({k}*{K_TICKS}-(2+2/{RHO}-1/({RHO}*(42-{k}))-1/({RHO}*(42-{k})*{K_TICKS}*{LCAP})))"
            f"/({K_TICKS}*{LSTAR})"
        )
        cand.append({"family": "G_2pi_abcorr_rho_modecorr_caparm", "expr": expr})

    # Family H: cap-arming with duty factor (Core-only, no facit)
    # Replace the raw cap term by a Z3×cap duty-cycle weight: 20/21.
    # Interpretation: over a Z3×A/B superpacket of size 3*L_cap=21, one slot is
    # reserved for P-ARM arming/disarming, leaving 20 active slots.
    for k in div42:
        if k >= MODE_MAX:
            continue
        expr = (
            f"2*pi*({k}*{K_TICKS}-(2+2/{RHO}-1/({RHO}*(42-{k}))-20/(21*{RHO}*(42-{k})*{K_TICKS}*{LCAP})))"
            f"/({K_TICKS}*{LSTAR})"
        )
        cand.append({"family": "H_2pi_abcorr_rho_modecorr_caparm_duty", "expr": expr})

    # Family C: Xi = 1/N where N is a small set derived from C30 closures
    denoms = sorted({30, 42, 60, 90, 126, 180, 210, 252, 315, 360, 420, 630, 840, 1260})
    for d in denoms:
        cand.append({"family": "C_unit_over_d", "expr": f"1/{d}"})

    # Family D: cap-shifted closure (still Core integers)
    # Xi = 1/(L* - L_cap) and Xi = 1/(L* + L_cap)
    cand.append({"family": "D_cap_shift", "expr": f"1/{LSTAR - LCAP}"})
    cand.append({"family": "D_cap_shift", "expr": f"1/{LSTAR + LCAP}"})

    # Attach complexity + deterministic ordering id
    for i, c in enumerate(cand):
        c["complexity"] = list(_complexity(c["expr"]))
        c["id"] = f"X{i:03d}"

    cand.sort(key=lambda x: tuple(x["complexity"]) + (x["family"], x["expr"]))
    return cand


def _safe_eval_expr(expr: str) -> float:
    """Evaluate a tiny expression language used in this lock.

    Allowed tokens: digits, + - * / parentheses, and 'pi'.
    """
    for ch in expr:
        if ch.isdigit() or ch in "+-*/(). " or ch.isalpha():
            continue
        raise ValueError(f"illegal char in expr: {ch!r}")
    # reject any names other than pi
    names = "".join([c if c.isalpha() else " " for c in expr]).split()
    if any(n != "pi" for n in names):
        raise ValueError(f"illegal name(s) in expr: {names}")
    return float(eval(expr, {"__builtins__": {}}, {"pi": math.pi}))


def _half_expr(expr: str) -> str:
    """Return expr/2 in a deterministic, minimal form for our tiny language."""
    e = expr.strip()
    # 2*pi*k/L* -> pi*k/L*
    if e.startswith("2*pi*"):
        return "pi*" + e[len("2*pi*") :]
    # pure rational k/L -> k/(2L) with gcd simplification
    if "/" in e and "pi" not in e and "*" not in e:
        a, b = e.split("/", 1)
        try:
            num = int(a)
            den = int(b)
            den2 = 2 * den
            g = math.gcd(num, den2)
            num //= g
            den2 //= g
            return f"{num}/{den2}"
        except Exception:
            pass
    # 1/d -> 1/(2d)
    if e.startswith("1/") and "pi" not in e and "*" not in e:
        try:
            den = int(e[len("1/") :])
            return f"1/{2*den}"
        except Exception:
            pass
    return f"({e})/2"


def main() -> int:
    out_dir = REPO / "out" / f"CORE_{LOCK}"
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates = _build_candidates()

    # Deterministic *preferred* candidate (facit-free): the first in the internal
    # complexity ordering. We keep the full set; this is only a convention used
    # for downstream “preferred” propagation.
    preferred_xi = candidates[0] if candidates else None

    # Attach numeric approximations for Xi_RT and derived alpha_RT candidates.
    alpha_candidates = []
    for c in candidates:
        xi_expr = str(c.get("expr"))
        try:
            xi_val = _safe_eval_expr(xi_expr)
        except Exception:
            xi_val = None
        a_expr = _half_expr(xi_expr)
        try:
            a_val = _safe_eval_expr(a_expr)
        except Exception:
            a_val = None
        c["approx"] = {"Xi_RT": xi_val}
        alpha_candidates.append({
            "id": c.get("id"),
            "source_xi_expr": xi_expr,
            "expr": a_expr,
            "approx": a_val,
        })

    preferred_alpha = None
    if preferred_xi:
        pid = preferred_xi.get("id")
        for a in alpha_candidates:
            if a.get("id") == pid:
                preferred_alpha = a
                break

    # Note: we intentionally do NOT pick a single Xi_RT here; this stays a
    # candidate-set until a Core-only lock removes the degeneracy.

    # Reduced view (facit-free): canonical small-denominator subset of the 1/d family.
    canon_denoms = [30, 42, 60, 90, 1260]
    xi_canon = []
    for c in candidates:
        if isinstance(c, dict) and c.get("family") == "C_unit_over_d":
            expr = str(c.get("expr"))
            if expr.startswith("1/"):
                try:
                    d = int(expr[2:])
                except Exception:
                    d = None
                if d in set(canon_denoms):
                    xi_canon.append(c)

    out = {
        "version": "v0.6",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "lock": LOCK,
        "derivation_status": "CANDIDATE-SET",
        "validation_status": "UNTESTED",
        "core_definition": {
            "Xi_RT": {
                "type": "symbolic_constant",
                "unit": "dimensionless",
                "definition": "Xi_RT := 2 * alpha_RT (RT internal).",
            },
            "alpha_RT": {
                "type": "derived_symbol",
                "unit": "dimensionless",
                "definition": "alpha_RT := Xi_RT / 2 (definition; Xi_RT unknown in Core at this stage).",
            },
            "Z_RT": {
                "type": "symbolic_scale",
                "unit": "dimensionless",
                "definition": "Intrinsic RT-impedance scale (SI Z0 appears only in Overlay/Compare).",
            },
            "G_RT(nu)": {
                "type": "symbolic_family",
                "unit": "dimensionless",
                "definition": "Intrinsic RT-conductance chain for mode nu (SI G0 only in Overlay/Compare).",
            },
            "family_relation": "Z_RT * G_RT(nu) = 2 * nu * alpha_RT (structure; no numeric fixing in Core yet).",
        },
        "candidate_space": {
            "Xi_RT": {
                "type": "finite_candidate_set",
                "candidates": candidates,
                "reduced_views": {
                    "canon_denoms": {
                        "note": "Subset of family C (1/d) with d in {30,42,60,90,1260}; optional view (facit-free).",
                        "denoms": canon_denoms,
                        "candidates": xi_canon,
                        "preferred": (xi_canon[0] if xi_canon else None),
                    }
                },
                "preferred": {
                    "id": preferred_xi.get("id"),
                    "expr": preferred_xi.get("expr"),
                    "approx": (preferred_xi.get("approx") or {}).get("Xi_RT"),
                    "rule": "min_complexity (token_count, has_pi, digit_count, expr_len) + (family, expr)",
                }
                if preferred_xi
                else None,
                "note": "Generated from Core integers (L*=1260, cap=7, C30/divisors) + math constants; no facit used.",
            },
            "alpha_RT": {
                "type": "derived_candidate_set",
                "derived_from": "Xi_RT/2",
                "candidates": alpha_candidates,
                "preferred": {
                    "id": preferred_alpha.get("id"),
                    "expr": preferred_alpha.get("expr"),
                    "approx": preferred_alpha.get("approx"),
                    "rule": "inherits preferred Xi_RT via alpha_RT := Xi_RT/2",
                }
                if preferred_alpha
                else None,
                "note": "alpha_RT candidates are derived from Xi_RT candidates by alpha_RT := Xi_RT/2 (no selection).",
            },
        },
        "tie_break": {
            "rule": "Order candidates by internal complexity (token_count, has_pi, digit_count, expr_len), then (family, expr).",
            "selected": None,
            "preferred": {
                "Xi_RT": {
                    "id": preferred_xi.get("id"),
                    "expr": preferred_xi.get("expr"),
                    "approx": (preferred_xi.get("approx") or {}).get("Xi_RT"),
                }
                if preferred_xi
                else None,
                "alpha_RT": {
                    "id": preferred_alpha.get("id"),
                    "expr": preferred_alpha.get("expr"),
                    "approx": preferred_alpha.get("approx"),
                }
                if preferred_alpha
                else None,
            },
            "note": "Full candidate-set is retained. 'preferred' is a deterministic, facit-free convention only.",
        },
        "notes": [
            "Core contains only structural definitions + a facit-free candidate generator.",
            "Overlay may later map (Z_RT,G_RT) to (Z0,G0) for comparison, but must not feed back.",
            "Bf/Tick/c remain symbolic in Core; Bf not used numerically.",
        ],
    }

    p = out_dir / "em_lock_core_v0_6.json"
    p.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # small markdown for human scan
    md = out_dir / "em_lock_core_v0_6.md"
    md.write_text(
        "\n".join(
            [
                "# EM_LOCK Core (v0.6)",
                "",
                "- Derivation-status: **CANDIDATE-SET**",
                "- Validation-status: **UNTESTED**",
                "",
                "## Core definition (symbolic)",
                "",
                "- Xi_RT := 2 * alpha_RT",
                "- alpha_RT := Xi_RT/2",
                "- Z_RT, G_RT(nu): intrinsic RT scales (dimensionless in Core)",
                "- Relation: Z_RT * G_RT(nu) = 2*nu*alpha_RT",
                "",
                "## Candidate space (finite set, ordered by internal complexity)",
                f"- Generated from Core integers: L*={LSTAR}, cap={LCAP}, divisors(42), and C30-derived denominators.",
                "- Xi_RT candidates are expressions (no facit selection).",
                "",
                "## Notes",
                "- No overlay/refs read. No score-to-facit used in generation or ordering.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"WROTE: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
