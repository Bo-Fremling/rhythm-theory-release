#!/usr/bin/env python3
"""EM Xi invariant lock (Core-only; NO-FACIT).

Purpose
- Provide a *proof artifact* for the cap-duty factor used by EM family H:
      duty := 20/21.
- This is purely Core-internal: derived from Z3-sectorality (3) and the
  Global Frame cap magnitude |L_cap|=7 (bias-nollning sextet 6 + P-ARM 1).

Interpretation (Core semantics)
- Global frame closure: L_* = 1260 = 30·42.
- Cap magnitude: |L_cap| = 6 + 1 = 7.
- Z3 sectors: 3.
- Superpacket size: N = 3·|L_cap| = 21.
- One slot is reserved for P-ARM (arming/disarming), leaving N-1=20 active.
- Therefore duty = (N-1)/N = 20/21.

This lock does NOT fit to any external numbers and must not read overlay.

Writes
  out/CORE_EM_XI_INVARIANT_LOCK/em_xi_invariant_lock_core_v0_1.json
  out/CORE_EM_XI_INVARIANT_LOCK/em_xi_invariant_lock_core_v0_1.md
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from fractions import Fraction
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _load_cap_pack() -> dict:
    """Load cap from CORE_GLOBAL_FRAME_CAP_LOCK if present; else derive locally."""
    jp = REPO / "out" / "CORE_GLOBAL_FRAME_CAP_LOCK" / "global_frame_cap_lock_core_v0_1.json"
    if jp.exists():
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
            cap = data.get("cap") or {}
            return {
                "L_bias": int(cap.get("L_bias", 6)),
                "L_arm": int(cap.get("L_arm", 1)),
                "L_cap_mag": int(cap.get("L_cap_mag", 7)),
            }
        except Exception:
            pass
    # Fallback (Core canonical rule)
    L_bias, L_arm = 6, 1
    return {"L_bias": int(L_bias), "L_arm": int(L_arm), "L_cap_mag": int(L_bias + L_arm)}


@dataclass
class DutyFactor:
    expr: str
    value: float
    num: int
    den: int
    derived_from: dict


def main() -> int:
    # Core integers (no SI, no tuning)
    K = 30
    MODE = 42
    L_star = K * MODE  # 1260    # Derive |L_cap| via GLOBAL_FRAME_CAP_LOCK (preferred)
    cap_pack = _load_cap_pack()
    L_bias = int(cap_pack['L_bias'])
    L_arm = int(cap_pack['L_arm'])
    L_cap_mag = int(cap_pack['L_cap_mag'])


    # Z3 sectorality (Core axiom: slot labels k mod 3)
    Z3 = 3

    # Superpacket (Z3 × cap)
    N = int(Z3 * L_cap_mag)  # 21

    # P-ARM reserved slot
    reserved = 1
    active = int(N - reserved)  # 20

    duty = Fraction(active, N)  # 20/21

    duty_pack = DutyFactor(
        expr=f"{duty.numerator}/{duty.denominator}",
        value=float(duty),
        num=int(duty.numerator),
        den=int(duty.denominator),
        derived_from={
            "L_star": {"expr": f"{K}*{MODE}", "value": int(L_star)},
            "cap": {
                "expr": "|L_cap| := L_bias + L_arm",
                "L_bias": int(L_bias),
                "L_arm": int(L_arm),
                "value": int(L_cap_mag),
                "note": "bias-nollning sextet (6) + P-ARM (1)",
            },
            "Z3": {"expr": "Z3 := 3", "value": int(Z3)},
            "superpacket": {"expr": "N := Z3*|L_cap|", "value": int(N)},
            "P_ARM": {"expr": "reserved := 1", "value": int(reserved)},
            "active": {"expr": "active := N-reserved", "value": int(active)},
        },
    )

    # NEG diagnostics (should NOT be chosen in Core; just to document sensitivity)
    neg = []
    for bad_cap in (6, 8):
        N_bad = int(Z3 * bad_cap)
        duty_bad = Fraction(N_bad - reserved, N_bad)
        neg.append({
            "name": f"NEG_bad_cap_{bad_cap}",
            "cap_mag": int(bad_cap),
            "superpacket": int(N_bad),
            "duty": {"expr": f"{duty_bad.numerator}/{duty_bad.denominator}", "value": float(duty_bad)},
            "expect": "FAIL (wrong |L_cap|)",
        })
    for bad_z3 in (2, 4):
        N_bad = int(bad_z3 * L_cap_mag)
        duty_bad = Fraction(N_bad - reserved, N_bad)
        neg.append({
            "name": f"NEG_bad_Z3_{bad_z3}",
            "Z3": int(bad_z3),
            "superpacket": int(N_bad),
            "duty": {"expr": f"{duty_bad.numerator}/{duty_bad.denominator}", "value": float(duty_bad)},
            "expect": "FAIL (wrong Z3 sectorality)",
        })

    out = {
        "version": "v0_1",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "lock": "EM_XI_INVARIANT_LOCK",
        "derivation_status": "DERIVED",
        "core_definition": {
            "K": int(K),
            "MODE": int(MODE),
            "L_star": int(L_star),
            "L_cap_mag": int(L_cap_mag),
            "Z3": int(Z3),
        },
        "duty_factor": asdict(duty_pack),
        "neg_controls": neg,
        "notes": [
            "No overlay. No PDG/CODATA. No numerical Bf.",
            "This artifact is intended as a *proof input* for promoting alpha_RT (and hence g_weak) to DERIVED once a unique EM family is selected by Core-only consistency rules.",
        ],
    }

    out_dir = REPO / "out" / "CORE_EM_XI_INVARIANT_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    jp = out_dir / "em_xi_invariant_lock_core_v0_1.json"
    mp = out_dir / "em_xi_invariant_lock_core_v0_1.md"

    jp.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# EM Xi invariant lock (Core-only)",
        "",
        f"- generated_utc: {out['generated_utc']}",
        "",
        "## Derived invariants",
        f"- L_* = {L_star} (= {K}·{MODE})",
        f"- |L_cap| = {L_cap_mag} (= {L_bias}+{L_arm})",
        f"- Z3 = {Z3}",
        f"- N = Z3·|L_cap| = {N}",
        f"- reserved(P-ARM) = {reserved}",
        f"- active = {active}",
        f"- duty = active/N = **{duty_pack.expr}** = {duty_pack.value}",
        "",
        "## NEG controls (diagnostic)",
    ]
    for it in neg:
        lines.append(f"- {it['name']}: duty={it['duty']['expr']} (expect {it['expect']})")

    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"WROTE: {jp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
