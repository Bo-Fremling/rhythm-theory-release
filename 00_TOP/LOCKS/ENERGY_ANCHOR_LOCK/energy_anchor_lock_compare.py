#!/usr/bin/env python3
"""Compare stub (Overlay-only).

No comparison implemented yet. This exists to enforce the required split.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LOCK = Path(__file__).resolve().parent.name


def main() -> int:
    out_dir = REPO / "out" / f"COMPARE_{LOCK}"
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "version": "v0.0",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "lock": LOCK,
        "policy": {"overlay_only": True, "feeds_back": False},
        "validation_status": "UNTESTED",
        "compare": None,
    }

    p = out_dir / f"{LOCK.lower()}_compare_stub_v0_0.json"
    p.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
