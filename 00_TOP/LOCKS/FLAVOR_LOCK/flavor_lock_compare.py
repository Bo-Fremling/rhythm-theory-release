#!/usr/bin/env python3
"""FLAVOR_LOCK compare (Overlay-only).

Reads out/CORE_FLAVOR_LOCK/* and compares to overlay refs if present.
Never feeds back into Core selection.

Outputs:
  out/COMPARE_FLAVOR_LOCK/flavor_lock_compare_v0_1.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    core_dir = REPO / "out" / "CORE_FLAVOR_LOCK"
    out_dir = REPO / "out" / "COMPARE_FLAVOR_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    core_ud = core_dir / "flavor_ud_core_v0_9.json"
    core_enu = core_dir / "flavor_enu_core_v0_9.json"

    if not core_ud.exists() or not core_enu.exists():
        print("MISSING core artifacts; run flavor_lock_coregen.py first")
        return 2

    ud = _load_json(core_ud)
    enu = _load_json(core_enu)

    ref_path = REPO / "00_TOP" / "OVERLAY" / "sm29_data_reference.json"
    have_ref = ref_path.exists()
    ref = _load_json(ref_path) if have_ref else {}

    # Best-effort: compare only if refs exist; otherwise report UNTESTED.
    cmp = {"ckm": None, "pmns": None}
    if have_ref:
        try:
            ckm_ref = ref.get("CKM", {})
            pmns_ref = ref.get("PMNS", {})
            ckm = ud.get("CKM", {}).get("angles", {})
            pmns = enu.get("PMNS", {}).get("angles", {})

            def pack(pred: dict, targ: dict):
                out = {}
                for k in ["theta12_deg", "theta23_deg", "theta13_deg", "delta_deg_from_sin"]:
                    if k in pred and k in targ:
                        out[k] = {"pred": float(pred[k]), "ref": float(targ[k]), "diff": float(pred[k]) - float(targ[k])}
                return out

            cmp["ckm"] = pack(ckm, ckm_ref.get("angles", {}))
            cmp["pmns"] = pack(pmns, pmns_ref.get("angles", {}))
        except Exception:
            cmp = {"ckm": "compare_failed", "pmns": "compare_failed"}

    report = {
        "version": "v0.1",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "policy": {"overlay_only": True, "feeds_back": False},
        "inputs": {
            "core_ud": str(core_ud.relative_to(REPO)).replace("\\", "/"),
            "core_enu": str(core_enu.relative_to(REPO)).replace("\\", "/"),
            "ref": str(ref_path.relative_to(REPO)).replace("\\", "/") if have_ref else None,
        },
        "validation_status": "COMPARED" if have_ref else "UNTESTED",
        "compare": cmp,
    }

    out_json = out_dir / "flavor_lock_compare_v0_1.json"
    out_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
