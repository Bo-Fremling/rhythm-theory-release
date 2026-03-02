#!/usr/bin/env python3
"""GS_LOCK compare (Overlay-only).

Compares Core candidate-set for alpha_s_RT against overlay reference values.

This script MUST NOT be used as input to Core selection.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[3]
LOCK = Path(__file__).resolve().parent.name


def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _pick_latest(dirpath: Path, pattern: str) -> Optional[Path]:
    c = sorted(dirpath.glob(pattern))
    return c[-1] if c else None


def _pick_overlay_ref() -> Optional[Path]:
    overlay = REPO / "00_TOP" / "OVERLAY"
    c = sorted(overlay.glob("sm29_data_reference*.json"))
    return c[-1] if c else None


def main() -> int:
    core_dir = REPO / "out" / f"CORE_{LOCK}"
    core_path = _pick_latest(core_dir, "gs_lock_core_v*.json")
    if not core_path:
        print(f"MISSING: {core_dir}/gs_lock_core_v*.json")
        return 2

    core = _read_json(core_path)
    cands = (((core.get("candidate_space", {}) or {}).get("alpha_s_RT", {}) or {}).get("candidates", []) or [])

    ref_path = _pick_overlay_ref()
    refs = (_read_json(ref_path).get("refs") or {}) if ref_path else {}

    alpha_s_ref = None
    for key in ["alpha_s", "alpha_s_MZ", "alpha_s_RT"]:
        if key in refs:
            alpha_s_ref = refs.get(key)
            break

    out_dir = REPO / "out" / f"COMPARE_{LOCK}"
    out_dir.mkdir(parents=True, exist_ok=True)

    out = {
        "version": "v0.2",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "lock": LOCK,
        "policy": {"overlay_only": True, "feeds_back": False},
        "core": str(core_path.relative_to(REPO)).replace("\\", "/"),
        "overlay_ref": str(ref_path.relative_to(REPO)).replace("\\", "/") if ref_path else None,
        "alpha_s_ref": alpha_s_ref,
        "candidate_count": len(cands),
        "note": "Compare-only; does not affect Core candidate ordering/selection.",
    }

    jp = out_dir / "gs_lock_compare_v0_2.json"
    jp.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    mp = out_dir / "gs_lock_compare_v0_2.md"
    mp.write_text(
        "\n".join(
            [
                "# GS_LOCK compare (v0.2)",
                "",
                f"Core: `{out['core']}`",
                f"Overlay ref: `{out['overlay_ref']}`",
                f"alpha_s_ref: {alpha_s_ref}",
                f"candidate_count: {len(cands)}",
                "",
                "(Compare-only; no feedback to Core.)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"WROTE: {jp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
