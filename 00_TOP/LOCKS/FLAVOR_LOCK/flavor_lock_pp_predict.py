#!/usr/bin/env python3
"""Generate PP-based |V| and |U| predictions from deterministic RT-construct checks.

Policy
- No scan. No SI. Deterministic extraction from the *verify* result.
- CKM preferred: v0.24 (ρ² phaseful CKM13 in Uu right-basis PP23) if present; else v0.19; else v0.18; else seam-only.
- PMNS preferred (Goal-B): v0.27 (θ12 right-R12 sextet×mcap after v0.21) if present; else v0.22; else v0.21; else v0.20; else piggy-back on CKM node.

Outputs
- out/FLAVOR_LOCK/flavor_pp_pred_v0_1.json
- out/FLAVOR_LOCK/flavor_pp_pred_summary_v0_1.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple


REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = REPO_ROOT / "out" / "FLAVOR_LOCK"
VERIFY_JSON = OUT_DIR / "flavor_lock_verify_v0_1.json"

PREFERRED_KEYS_CKM = [
    "rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_CPBEST",
    "rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_holoC30_GRIDBEST",
    "rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB_CANON_ROWPHASE",
    "rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_sextet_phiB",
    "rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_rho2_phiB",
    "rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis",
    "rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23",
    "rt_construct_monodromy_1260_postR12_seam_from_phase_rule_down_oriented",
    "rt_construct_misalignment",

]

PREFERRED_KEYS_PMNS = [
    # Goal-B: PMNS θ23 lift (cap=7) + θ13 suppression (sextet engagement)
    "rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet_mcap",
    "rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7_pmns12_sextet",
    "rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet_pmns23_cap7",
    # fallback: PMNS θ13 suppression via sextet engagement
    "rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_pmns13_sextet",
    # fallback: share the CKM-preferred node
    "rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis",
    "rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23",
    "rt_construct_monodromy_1260_postR12_seam_from_phase_rule_down_oriented",
    "rt_construct_misalignment",
]


def _pick_by_preference(checks: Dict[str, Any], preferred: list[str]) -> Tuple[str, Dict[str, Any]]:
    for k in preferred:
        node = checks.get(k)
        if isinstance(node, dict) and not node.get("error") and ("CKM" in node or "PMNS" in node):
            return k, node
    # fallback: first dict-like
    for k, v in checks.items():
        if isinstance(v, dict) and ("CKM" in v or "PMNS" in v) and not v.get("error"):
            return k, v
    raise KeyError("no construct node found")


def _extract_composite(checks: Dict[str, Any]) -> Dict[str, Any]:
    k_ckm, node_ckm = _pick_by_preference(checks, PREFERRED_KEYS_CKM)
    k_pmns, node_pmns = _pick_by_preference(checks, PREFERRED_KEYS_PMNS)

    ckm = node_ckm.get("CKM") or {}
    pmns = node_pmns.get("PMNS") or {}

    picked_key = k_ckm if k_ckm == k_pmns else "COMPOSITE"
    picked_ver = (node_ckm.get("version") if k_ckm == k_pmns else "COMPOSITE")

    out: Dict[str, Any] = {
        "version": "flavor_pp_pred_v0_1",
        "picked_key": picked_key,
        "picked_key_ckm": k_ckm,
        "picked_key_pmns": k_pmns,
        "picked_construct_version": picked_ver,
        "picked_construct_version_ckm": node_ckm.get("version"),
        "picked_construct_version_pmns": node_pmns.get("version"),
        "policy_ckm": node_ckm.get("policy") or {},
        "policy_pmns": node_pmns.get("policy") or {},
        "CKM": {
            "V_abs": ckm.get("V_abs"),
            "angles": (ckm.get("angles") or {}),
            "unitary_residual": ckm.get("unitary_residual"),
        },
        "PMNS": {
            "U_abs": pmns.get("U_abs"),
            "angles": (pmns.get("angles") or {}),
            "unitary_residual": pmns.get("unitary_residual"),
        },
        "notes": [
            "PP-based (RT-construct) prediction extracted deterministically from verify output.",
            "Composite allowed: CKM and PMNS may come from different construct nodes (Goal-B).",
        ],
    }

    # If chosen CKM node stores a pre-step matrix, expose for audits.
    if isinstance(node_ckm, dict):
        if "CKM_pre_pp23" in node_ckm:
            out["CKM_pre_pp23"] = node_ckm.get("CKM_pre_pp23")
        elif "CKM_pre_pp23_uubasis" in node_ckm:
            out["CKM_pre_pp23"] = node_ckm.get("CKM_pre_pp23_uubasis")

    return out


def main() -> int:
    if not VERIFY_JSON.exists():
        raise SystemExit(f"missing verify json: {VERIFY_JSON}")

    data = json.loads(VERIFY_JSON.read_text(encoding="utf-8"))
    checks = data.get("checks") or {}

    pred = _extract_composite(checks)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "flavor_pp_pred_v0_1.json"
    out_md = OUT_DIR / "flavor_pp_pred_summary_v0_1.md"

    out_json.write_text(json.dumps(pred, indent=2, sort_keys=True), encoding="utf-8")

    ck = pred.get("CKM", {}).get("angles", {})
    pm = pred.get("PMNS", {}).get("angles", {})

    def _fmt(a: Dict[str, Any]) -> str:
        def f(k: str) -> str:
            v = a.get(k)
            return "—" if v is None else f"{float(v):.6g}"

        return (
            f"θ12={f('theta12_deg')}°, θ23={f('theta23_deg')}°, θ13={f('theta13_deg')}°, "
            f"δ≈{f('delta_deg_from_sin')}°, J={f('J')}"
        )

    md = []
    md.append("# FLAVOR_LOCK PP prediction (v0.1)\n")
    md.append(f"\n- source: {VERIFY_JSON.name}")
    md.append(f"\n- picked_key: {pred.get('picked_key')}")
    md.append(f"\n- picked_key_ckm: {pred.get('picked_key_ckm')}")
    md.append(f"\n- picked_key_pmns: {pred.get('picked_key_pmns')}")
    md.append(f"\n- construct_version_ckm: {pred.get('picked_construct_version_ckm')}")
    md.append(f"\n- construct_version_pmns: {pred.get('picked_construct_version_pmns')}\n")

    md.append("## CKM (pred)\n")
    md.append("- " + _fmt(ck) + "\n")
    md.append("## PMNS (pred)\n")
    md.append("- " + _fmt(pm) + "\n")

    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())