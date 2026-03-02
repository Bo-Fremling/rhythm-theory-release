#!/usr/bin/env python3
"""NU_MECHANISM_LOCK compare (Overlay-only).

Reads out/CORE_NU_MECHANISM_LOCK/* and compares to overlay refs if present.
Never feeds back into Core selection.

Outputs:
  out/COMPARE_NU_MECHANISM_LOCK/nu_mechanism_lock_compare_v0_0.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    core = REPO / "out" / "CORE_NU_MECHANISM_LOCK" / "nu_mechanism_lock_v0_3.json"
    out_dir = REPO / "out" / "COMPARE_NU_MECHANISM_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not core.exists():
        print("MISSING core artifact; run nu_mechanism_lock_coregen.py first")
        return 2

    ref_path = REPO / "00_TOP" / "OVERLAY" / "sm29_data_reference.json"
    have_ref = ref_path.exists()
    ref = _load_json(ref_path) if have_ref else {}
    core_obj = _load_json(core)

    # Best-effort: compare the Δm^2 ratio if available.
    cmp = None
    if have_ref:
        try:
            pred = (core_obj.get("best", {}) or {}).get("dm2_ratio", None)
            targ = (((ref.get("NEUTRINO", {}) or {}).get("dm2_ratio", None)))
            if pred is not None and targ is not None:
                cmp = {"dm2_ratio": {"pred": float(pred), "ref": float(targ), "diff": float(pred) - float(targ)}}
        except Exception:
            cmp = "compare_failed"

    report = {
        "version": "v0.0",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "policy": {"overlay_only": True, "feeds_back": False},
        "inputs": {
            "core": str(core.relative_to(REPO)).replace("\\", "/"),
            "ref": str(ref_path.relative_to(REPO)).replace("\\", "/") if have_ref else None,
        },
        "validation_status": "COMPARED" if have_ref else "UNTESTED",
        "compare": cmp,
    }

    out = out_dir / "nu_mechanism_lock_compare_v0_0.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
