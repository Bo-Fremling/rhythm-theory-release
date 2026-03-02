#!/usr/bin/env python3
"""GLOBAL_FRAME_CAP_LOCK coregen (Core-only; NO-FACIT).

Purpose
- Make the Global Frame cap parameter explicit in Core:
    |L_cap| = 7 and canonical sign L_cap = -|L_cap|.
- Provide NEG controls that show nearby alternatives are rejected by Core-only
  invariants (symmetry + minimality), not by any external scoring.

Core rule (canonical)
- Z3×A/B symmetry implies a sextet unit for bias-nollning: L_bias ≡ 0 (mod 6).
- Choose the minimal positive sextet: L_bias := 6.
- P-ARM reserves one arming/disarming tick: L_arm := 1 (minimal positive).
- Therefore |L_cap| := L_bias + L_arm = 7.
- Sign rule: removed_endcap => L_cap := -|L_cap| (NEG flips sign).

Writes
  out/CORE_GLOBAL_FRAME_CAP_LOCK/global_frame_cap_lock_core_v0_1.json
  out/CORE_GLOBAL_FRAME_CAP_LOCK/global_frame_cap_lock_core_v0_1.md

Policy
- Must not read overlay or any *reference*.json
- Must not score vs PDG/CODATA/targets
"""

from __future__ import annotations

import json
from datetime import datetime
from fractions import Fraction
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LOCK = Path(__file__).resolve().parent.name

# Core invariants
Z3 = 3
AB = 2
SEXTET = Z3 * AB  # 6


def _derive_cap() -> dict:
    # Minimal sextet bias-nollning
    L_bias = int(SEXTET)  # minimal positive multiple of 6

    # Minimal arming/disarming
    L_arm = 1

    L_cap_mag = int(L_bias + L_arm)
    L_cap = int(-L_cap_mag)  # canonical sign: removed_endcap

    # Diagnostic: Z3×cap superpacket used elsewhere (e.g. duty 20/21)
    N = int(Z3 * L_cap_mag)
    reserved = 1
    duty = Fraction(N - reserved, N)

    return {
        "L_bias": int(L_bias),
        "L_arm": int(L_arm),
        "L_cap_mag": int(L_cap_mag),
        "L_cap": int(L_cap),
        "sign_rule": "removed_endcap => L_cap=-|L_cap|",
        "superpacket": {"expr": "N := Z3*|L_cap|", "N": int(N), "Z3": int(Z3)},
        "duty_diag": {"expr": f"{duty.numerator}/{duty.denominator}", "value": float(duty)},
    }


def _neg_controls(cap: dict) -> list[dict]:
    neg: list[dict] = []

    # Wrong bias length (still mod 6 but not minimal)
    for L_bias_bad in (0, 12, 18):
        if L_bias_bad <= 0:
            expect = "FAIL (bias-nollning requires positive sextet multiple)"
        else:
            expect = "FAIL (min-complexity prefers minimal sextet L_bias=6)"
        L_arm = int(cap["L_arm"])
        L_cap_mag = int(L_bias_bad + L_arm)
        N = int(Z3 * L_cap_mag) if L_cap_mag > 0 else 0
        duty = None
        if N > 0:
            duty = Fraction(N - 1, N)
        neg.append(
            {
                "name": f"NEG_bias_{L_bias_bad}",
                "L_bias": int(L_bias_bad),
                "L_arm": int(L_arm),
                "L_cap_mag": int(L_cap_mag),
                "superpacket_N": int(N),
                "duty": None if duty is None else {"expr": f"{duty.numerator}/{duty.denominator}", "value": float(duty)},
                "expect": expect,
            }
        )

    # Wrong arming (0 or >1)
    for L_arm_bad in (0, 2):
        L_bias = int(cap["L_bias"])
        L_cap_mag = int(L_bias + L_arm_bad)
        N = int(Z3 * L_cap_mag)
        duty = Fraction(N - 1, N)
        expect = "FAIL (P-ARM requires exactly one reserved arming/disarming tick)" if L_arm_bad == 0 else "FAIL (min-complexity prefers minimal arming L_arm=1)"
        neg.append(
            {
                "name": f"NEG_arm_{L_arm_bad}",
                "L_bias": int(L_bias),
                "L_arm": int(L_arm_bad),
                "L_cap_mag": int(L_cap_mag),
                "superpacket_N": int(N),
                "duty": {"expr": f"{duty.numerator}/{duty.denominator}", "value": float(duty)},
                "expect": expect,
            }
        )

    # Sign flip NEG
    neg.append(
        {
            "name": "NEG_sign_flip",
            "L_cap": int(abs(int(cap["L_cap"]))),
            "expect": "FAIL (canonical sign is removed_endcap => negative cap)"
        }
    )

    return neg


def main() -> int:
    out_dir = REPO / "out" / f"CORE_{LOCK}"
    out_dir.mkdir(parents=True, exist_ok=True)

    cap = _derive_cap()
    neg = _neg_controls(cap)

    out = {
        "version": "v0_1",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "lock": LOCK,
        "derivation_status": "DERIVED",
        "validation_status": "UNTESTED",
        "core_definition": {
            "Z3": int(Z3),
            "AB": int(AB),
            "sextet": int(SEXTET),
            "rule": "|L_cap| := L_bias + L_arm with L_bias=6 (min sextet), L_arm=1 (P-ARM)",
        },
        "cap": cap,
        "neg_controls": neg,
        "notes": [
            "No overlay. No PDG/CODATA. No numerical Bf.",
            "This lock exists to remove implicit cap=7 assumptions from other coregen scripts.",
        ],
    }

    jp = out_dir / "global_frame_cap_lock_core_v0_1.json"
    mp = out_dir / "global_frame_cap_lock_core_v0_1.md"
    jp.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# GLOBAL_FRAME_CAP_LOCK (Core-only)",
        "",
        f"- generated_utc: {out['generated_utc']}",
        "",
        "## Derived cap",
        f"- sextet = Z3×A/B = {SEXTET}",
        f"- L_bias = {cap['L_bias']} (min positive sextet)",
        f"- L_arm = {cap['L_arm']} (P-ARM)",
        f"- |L_cap| = {cap['L_cap_mag']} (= L_bias+L_arm)",
        f"- L_cap = {cap['L_cap']} (sign rule: {cap['sign_rule']})",
        "",
        "## Diagnostics",
        f"- N = {cap['superpacket']['N']} (= Z3·|L_cap|)",
        f"- duty_diag = {cap['duty_diag']['expr']}",
        "",
        "## NEG controls",
    ]
    for it in neg:
        lines.append(f"- {it['name']}: expect {it['expect']}")

    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"WROTE: {jp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
