#!/usr/bin/env python3
"""Core stub (NO-FACIT).

This lock is intentionally BLANK/HYP in Core until a SI-free Core definition exists.
Writes only to out/CORE_<LOCK>/.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LOCK = Path(__file__).resolve().parent.name


def main() -> int:
    out_dir = REPO / "out" / f"CORE_{LOCK}"
    out_dir.mkdir(parents=True, exist_ok=True)

    out = {
        "version": "v0.0",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "lock": LOCK,
        "core_definition": None,
        "derivation_status": "BLANK",
        "validation_status": "UNTESTED",
        "notes": [
            "Core must stay SI-free and cannot use overlay refs.",
            "Implement a true Core definition before promoting this lock.",
        ],
    }

    p = out_dir / f"{LOCK.lower()}_core_blank_v0_0.json"
    p.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
