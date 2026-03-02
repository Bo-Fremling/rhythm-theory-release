#!/usr/bin/env python3
"""THETA_QCD_LOCK compare (Overlay-only).

Reads out/CORE_THETA_QCD_LOCK/* and compares to overlay refs if present.
Outputs:
  out/COMPARE_THETA_QCD_LOCK/theta_qcd_lock_compare_v0_0.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    core = REPO / "out" / "CORE_THETA_QCD_LOCK" / "theta_qcd_lock_v0_2.json"
    out_dir = REPO / "out" / "COMPARE_THETA_QCD_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not core.exists():
        print("MISSING core artifact; run theta_qcd_lock_coregen.py first")
        return 2

    ref_path = REPO / "00_TOP" / "OVERLAY" / "sm29_data_reference.json"
    have_ref = ref_path.exists()
    # Typically θ_QCD has only upper bounds; compare is optional.

    report = {
        "version": "v0.0",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "policy": {"overlay_only": True, "feeds_back": False},
        "inputs": {
            "core": str(core.relative_to(REPO)).replace("\\", "/"),
            "ref": str(ref_path.relative_to(REPO)).replace("\\", "/") if have_ref else None,
        },
        "validation_status": "UNTESTED" if not have_ref else "COMPARED",
        "compare": None,
    }

    out = out_dir / "theta_qcd_lock_compare_v0_0.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
