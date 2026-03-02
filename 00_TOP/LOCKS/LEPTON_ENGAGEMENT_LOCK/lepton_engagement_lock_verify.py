#!/usr/bin/env python3
"""Verify LEPTON_ENGAGEMENT_LOCK outputs (policy gates; no tuning).

Notes
-----
- `overall` is **policy/sanity only** (discreteness + bounds). It does NOT require PDG match.
- PDG (Overlay) ratio checks are reported under `overlay_match` and do not affect `overall`.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

LSTAR = 1260
STEP = 6


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def safe_ratio(a: float, b: float) -> float:
    return float(a) / float(b)


def main() -> int:
    jpath = REPO_ROOT / "out" / "LEPTON_ENGAGEMENT_LOCK" / "lepton_engagement_lock_v0_1.json"
    if not jpath.exists():
        print(f"MISSING: {jpath}")
        return 2

    obj = load_json(jpath)
    N = (obj.get("best", {}) or {}).get("N_act", {}) or {}
    Ne = int(N.get("e"))
    Nmu = int(N.get("mu"))
    Ntau = int(N.get("tau"))

    gates = {}
    gates["N_act_multiple_of_6"] = (Ne % STEP == 0 and Nmu % STEP == 0 and Ntau % STEP == 0)
    gates["N_act_within_Lstar"] = (max(Ne, Nmu, Ntau) <= LSTAR)
    gates["monotone_order"] = (Ne <= Nmu <= Ntau)

    ok = all(gates.values())

    # ---- Overlay ratio match (informational; not affecting overall) ----
    overlay = {
        "present": False,
        "r_e_mu_ref": None,
        "r_mu_tau_ref": None,
        "r_e_mu_pred": safe_ratio(Ne, Nmu) if Nmu else None,
        "r_mu_tau_pred": safe_ratio(Nmu, Ntau) if Ntau else None,
        "tol_rel": 0.01,  # 1% default; strict on purpose
        "match": False,
    }

    ref_path = REPO_ROOT / "00_TOP" / "OVERLAY" / "sm29_data_reference_v0_1.json"
    if ref_path.exists():
        refs = (load_json(ref_path).get("refs", {}) or {})
        try:
            me = float(refs["m_e"]["value"])
            mmu = float(refs["m_mu"]["value"])
            mtau = float(refs["m_tau"]["value"])
            overlay["present"] = True
            overlay["r_e_mu_ref"] = safe_ratio(me, mmu)
            overlay["r_mu_tau_ref"] = safe_ratio(mmu, mtau)

            def rel_ok(pred: float, ref: float, tol_rel: float) -> bool:
                if pred is None or ref is None or ref == 0:
                    return False
                return abs(pred - ref) / abs(ref) <= tol_rel

            ok12 = rel_ok(overlay["r_e_mu_pred"], overlay["r_e_mu_ref"], overlay["tol_rel"])
            ok23 = rel_ok(overlay["r_mu_tau_pred"], overlay["r_mu_tau_ref"], overlay["tol_rel"])
            overlay["match"] = bool(ok12 and ok23)
            overlay["match_detail"] = {"r_e_mu": ok12, "r_mu_tau": ok23}
        except Exception:
            overlay["present"] = False

    out = {
        "version": "v0.2",
        "inputs": {"json": str(jpath.relative_to(REPO_ROOT))},
        "policy": {"L_star": LSTAR, "step": STEP},
        "gates": gates,
        "overall": "PASS" if ok else "FAIL",
        "overlay_match": overlay,
    }

    out_dir = REPO_ROOT / "out" / "LEPTON_ENGAGEMENT_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "lepton_engagement_lock_verify_v0_2.json").write_text(
        json.dumps(out, indent=2, sort_keys=True), encoding="utf-8"
    )

    lines = [
        "# LEPTON_ENGAGEMENT_LOCK verify (v0.2)",
        "",
        "Policy / sanity gates (affects overall):",
        f"- N_act_multiple_of_6: {'PASS' if gates['N_act_multiple_of_6'] else 'FAIL'}",
        f"- N_act_within_Lstar: {'PASS' if gates['N_act_within_Lstar'] else 'FAIL'}",
        f"- monotone_order: {'PASS' if gates['monotone_order'] else 'FAIL'}",
        "",
        f"Overall (policy only): {'PASS' if ok else 'FAIL'}",
        "",
        "Overlay ratio match (informational; does NOT affect overall):",
    ]

    if overlay["present"]:
        lines += [
            f"- tol_rel: {overlay['tol_rel']}",
            f"- r_e/mu: pred={overlay['r_e_mu_pred']:.12g}, ref={overlay['r_e_mu_ref']:.12g} => {'PASS' if overlay.get('match_detail',{}).get('r_e_mu') else 'FAIL'}",
            f"- r_mu/tau: pred={overlay['r_mu_tau_pred']:.12g}, ref={overlay['r_mu_tau_ref']:.12g} => {'PASS' if overlay.get('match_detail',{}).get('r_mu_tau') else 'FAIL'}",
            f"- match_all: {'PASS' if overlay['match'] else 'FAIL'}",
        ]
    else:
        lines += ["- ref missing or unreadable"]

    (out_dir / "lepton_engagement_lock_verify_summary_v0_2.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
