#!/usr/bin/env python3
"""Verify LEPTON_MASS_LOCK outputs.

Policy gates only (discrete + bounds). Overlay match is informational.
Prefers v0.5 if present, otherwise falls back to v0.4, then v0.3, then v0.2, then v0.1.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LSTAR = 1260
LCAP = 7
SEXTET = 6
NE_ACT = 42


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    cand_paths = [
        REPO_ROOT / "out" / "LEPTON_MASS_LOCK" / "lepton_mass_lock_v0_5.json",
        REPO_ROOT / "out" / "LEPTON_MASS_LOCK" / "lepton_mass_lock_v0_4.json",
        REPO_ROOT / "out" / "LEPTON_MASS_LOCK" / "lepton_mass_lock_v0_3.json",
        REPO_ROOT / "out" / "LEPTON_MASS_LOCK" / "lepton_mass_lock_v0_2.json",
        REPO_ROOT / "out" / "LEPTON_MASS_LOCK" / "lepton_mass_lock_v0_1.json",
    ]

    jpath = None
    for p in cand_paths:
        if p.exists():
            jpath = p
            break

    if jpath is None:
        print("MISSING: out/LEPTON_MASS_LOCK/lepton_mass_lock_v0_3.json (and v0_2/v0_1)")
        return 2

    obj = load_json(jpath)
    best = ((obj.get("model") or {}).get("best") or {})
    d = (best.get("d") or {})

    try:
        de = int(d.get("e"))
        dmu = int(d.get("mu"))
        dtau = int(d.get("tau"))
    except Exception:
        de = dmu = dtau = -1

    gates = {
        "d_within_bounds": (1 <= dtau <= dmu <= de <= (LSTAR - 1)),
        "monotone": (de >= dmu >= dtau),
    }

    # v0.5 structural gates (pure Core integers)
    if obj.get("version") == "v0.5":
        p12 = int(best.get("p12") or -1)
        p23 = int(best.get("p23") or -1)
        N = (best.get("N_act") or {})
        try:
            Ne = int(N.get("e"))
            Nmu = int(N.get("mu"))
            Ntau = int(N.get("tau"))
        except Exception:
            Ne = Nmu = Ntau = -1

        gates["v05_p_exponents"] = (p12 == 2 * LCAP + SEXTET and p23 == max(2, LCAP - 2))
        gates["v05_Nbase_offsets"] = (
            (Ne + LCAP == 3 * NE_ACT) and
            (Nmu - (LCAP + 1) == 9 * NE_ACT) and
            (Ntau - LCAP == 18 * NE_ACT)
        )
        gates["v05_d_matches_N"] = (
            de == LSTAR - Ne and dmu == LSTAR - Nmu and dtau == LSTAR - Ntau
        )

    # v0.1 has a step-of-6 constraint; v0.2 does not.
    if obj.get("version") == "v0.1":
        gates["d_multiple_of_6"] = (de % 6 == 0 and dmu % 6 == 0 and dtau % 6 == 0)

    ok = all(gates.values())

    core_err = best.get("errors_rel")
    core_max = None
    try:
        e = core_err or {}
        core_max = max(abs(float(e.get("mu_over_e"))), abs(float(e.get("tau_over_mu"))))
    except Exception:
        core_max = None

    ov = obj.get("overlay_triage") or {}
    ov_err = ov.get("errors_rel") if isinstance(ov, dict) else None
    ov_max = None
    try:
        e = ov_err or {}
        ov_max = max(abs(float(e.get("mu_over_e"))), abs(float(e.get("tau_over_mu"))))
    except Exception:
        ov_max = None

    out = {
        "version": obj.get("version"),
        "inputs": {"json": str(jpath.relative_to(REPO_ROOT))},
        "policy": {"L_star": LSTAR},
        "gates": gates,
        "overall": "PASS" if ok else "FAIL",
        "triage": {
            "core_target": {"errors_rel": core_err, "max_rel_err": core_max},
            "overlay" : {"errors_rel": ov_err, "max_rel_err": ov_max},
        },
    }

    out_dir = REPO_ROOT / "out" / "LEPTON_MASS_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "lepton_mass_lock_verify_latest.json").write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        f"# LEPTON_MASS_LOCK verify ({obj.get('version')})",
        "",
        "Policy gates:",
    ]
    for k, v in gates.items():
        lines.append(f"- {k}: {'PASS' if v else 'FAIL'}")
    lines += [
        "",
        f"Overall (policy only): {'PASS' if ok else 'FAIL'}",
        "",
        "Triage (informational):",
        f"- max_rel_err_vs_core_target: {core_max}",
        f"- max_rel_err_vs_overlay: {ov_max}",
    ]

    (out_dir / "lepton_mass_lock_verify_latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
