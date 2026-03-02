#!/usr/bin/env python3
"""LEPTON_MASS_LOCK compare (Overlay-only).

Compares *dimensionless* lepton mass ratios from Core against overlay refs.

Core is allowed to produce only ratios (no SI scale). This compare script
computes reference ratios from overlay m_e/m_mu/m_tau and checks tolerances.

Outputs:
  out/COMPARE_LEPTON_MASS_LOCK/lepton_mass_lock_compare_v0_2.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[3]


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _pick_overlay_ref() -> Optional[Path]:
    overlay = REPO / "00_TOP" / "OVERLAY"
    cands = sorted(overlay.glob("sm29_data_reference*.json"))
    return cands[-1] if cands else None


def _ref_ratios(refs: dict) -> Optional[dict]:
    try:
        me = refs.get("m_e") or {}
        mm = refs.get("m_mu") or {}
        mt = refs.get("m_tau") or {}
        if "value" not in me or "value" not in mm or "value" not in mt:
            return None
        me_v = float(me["value"])
        mm_v = float(mm["value"])
        mt_v = float(mt["value"])
        r1 = mm_v / me_v
        r2 = mt_v / mm_v
        # conservative tol propagation: sum of component rel-tols
        tol1 = float(mm.get("tol_rel", 0.0)) + float(me.get("tol_rel", 0.0))
        tol2 = float(mt.get("tol_rel", 0.0)) + float(mm.get("tol_rel", 0.0))
        return {
            "m_mu_over_m_e": {"value": r1, "tol_rel": tol1},
            "m_tau_over_m_mu": {"value": r2, "tol_rel": tol2},
        }
    except Exception:
        return None


def _ok_rel(pred: float, ref: float, tol_rel: float) -> bool:
    if ref == 0:
        return abs(pred - ref) == 0
    return abs(pred - ref) <= abs(ref) * float(tol_rel)


def _compare_one(core_path: Path, rr: dict) -> dict:
    obj = _load_json(core_path)
    pred = (((obj.get("model") or {}).get("best") or {}).get("ratios_pred") or {})
    out = {"file": str(core_path.name)}

    for k in ["m_mu_over_m_e", "m_tau_over_m_mu"]:
        if k in rr and k in pred:
            pv = float(pred[k])
            rv = float(rr[k]["value"])
            tol = float(rr[k]["tol_rel"])
            out[k] = {
                "pred": pv,
                "ref": rv,
                "tol_rel": tol,
                "rel_err": (pv - rv) / rv,
                "ok": _ok_rel(pv, rv, tol),
            }
    return out


def main() -> int:
    core_dir = REPO / "out" / "CORE_LEPTON_MASS_LOCK"
    out_dir = REPO / "out" / "COMPARE_LEPTON_MASS_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    cores = [
        core_dir / "lepton_mass_lock_core_v0_4.json",
        core_dir / "lepton_mass_lock_core_v0_5.json",
    ]
    if not all(p.exists() for p in cores):
        print("MISSING core artifacts; run lepton_mass_lock_coregen.py first")
        return 2

    ref_path = _pick_overlay_ref()
    have_ref = ref_path is not None and ref_path.exists()
    ref = _load_json(ref_path) if have_ref else {}
    rr = _ref_ratios(ref.get("refs") or {}) if have_ref else None

    cmp = None
    status = "UNTESTED"
    if have_ref and rr:
        cmp = [_compare_one(p, rr) for p in cores]
        status = "COMPARED"

    report = {
        "version": "v0.2",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "policy": {"overlay_only": True, "feeds_back": False},
        "inputs": {
            "core": [(p.relative_to(REPO)).as_posix() for p in cores],
            "ref": (ref_path.relative_to(REPO)).as_posix() if have_ref else None,
        },
        "validation_status": status,
        "compare": cmp,
    }

    out = out_dir / "lepton_mass_lock_compare_v0_2.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
