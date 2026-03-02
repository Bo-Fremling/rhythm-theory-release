#!/usr/bin/env python3
"""EW_COUPLING_LOCK compare (Overlay-only).

Compares Core predictions/candidate-sets to overlay refs if present.

Outputs:
  out/COMPARE_EW_COUPLING_LOCK/ew_coupling_compare_v0_2.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[3]


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _pick_latest(pattern: str) -> Optional[Path]:
    cands = sorted((REPO / "out" / "CORE_EW_COUPLING_LOCK").glob(pattern))
    return cands[-1] if cands else None


def _pick_overlay_ref() -> Optional[Path]:
    overlay = REPO / "00_TOP" / "OVERLAY"
    cands = sorted(overlay.glob("sm29_data_reference*.json"))
    return cands[-1] if cands else None


def _as_float(x):
    try:
        return float(x)
    except Exception:
        return None


def _tol_ok(core_val: float, ref: dict) -> tuple[bool, str]:
    if "tol_abs" in ref:
        tol = float(ref["tol_abs"])
        ok = abs(core_val - float(ref["value"])) <= tol
        return ok, f"tol_abs={tol}"
    if "tol_rel" in ref:
        tol = float(ref["tol_rel"])
        rv = float(ref["value"])
        ok = abs(core_val - rv) <= tol * abs(rv)
        return ok, f"tol_rel={tol}"
    ok = core_val == float(ref.get("value"))
    return ok, "exact"


def main() -> int:
    core = _pick_latest("ew_coupling_core_v*.json")
    if not core:
        print("MISSING core artifact; run ew_coupling_lock_coregen.py first")
        return 2

    ref_path = _pick_overlay_ref()
    have_ref = bool(ref_path and ref_path.exists())
    ref = _load(ref_path) if have_ref else {}

    core_obj = _load(core)
    pred = core_obj.get("predictions", {})
    cs = core_obj.get("candidate_space") or {}
    refs = (ref.get("refs") or {}) if have_ref else {}

    cmp = None
    if have_ref:
        cmp = {}

        # weak coupling g at tree-level (Q→0); accept if ANY Core candidate hits.
        g_ref = refs.get("ew_g_tree_Q0")
        g_block = cs.get("g_weak") if isinstance(cs, dict) else None
        g_cands = (g_block or {}).get("candidates") if isinstance(g_block, dict) else None
        if g_ref and isinstance(g_cands, list) and g_cands:
            hit = None
            ok_any = False
            tol_used = None
            for c in g_cands:
                v = _as_float((c or {}).get("approx"))
                if v is None:
                    continue
                ok, tol = _tol_ok(v, g_ref)
                tol_used = tol
                if ok:
                    ok_any = True
                    hit = {"id": c.get("id"), "value": v, "expr": c.get("expr")}
                    break
            cmp["ew_g_tree_Q0"] = {
                "ok": ok_any,
                "tol": tol_used,
                "ref": g_ref.get("value"),
                "hit": hit,
                "candidate_count": len(g_cands),
            }

    report = {
        "version": "v0.2",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "policy": {"overlay_only": True, "feeds_back": False},
        "inputs": {
            "core": str(core.relative_to(REPO)).replace("\\", "/"),
            "ref": str(ref_path.relative_to(REPO)).replace("\\", "/") if have_ref else None,
        },
        "validation_status": "COMPARED" if have_ref else "UNTESTED",
        "compare": cmp,
    }

    out_dir = REPO / "out" / "COMPARE_EW_COUPLING_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "ew_coupling_compare_v0_2.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
