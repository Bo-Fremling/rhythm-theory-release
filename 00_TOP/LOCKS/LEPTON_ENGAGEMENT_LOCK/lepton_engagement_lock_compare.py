#!/usr/bin/env python3
"""LEPTON_ENGAGEMENT_LOCK compare.

No canonical PDG/CODATA scalar to compare against (by design). This script just
packages the Core result as COMPARED=UNTESTED placeholder.

Outputs:
  out/COMPARE_LEPTON_ENGAGEMENT_LOCK/lepton_engagement_lock_compare_v0_0.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def main() -> int:
    core = REPO / "out" / "CORE_LEPTON_ENGAGEMENT_LOCK" / "lepton_engagement_lock_core_v0_1.json"
    if not core.exists():
        print("MISSING core artifact; run lepton_engagement_lock_coregen.py first")
        return 2

    out_dir = REPO / "out" / "COMPARE_LEPTON_ENGAGEMENT_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "version": "v0.0",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "policy": {"overlay_only": True, "feeds_back": False},
        "inputs": {"core": str(core.relative_to(REPO)).replace("\\", "/")},
        "validation_status": "UNTESTED",
        "compare": None,
    }

    out = out_dir / "lepton_engagement_lock_compare_v0_0.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
