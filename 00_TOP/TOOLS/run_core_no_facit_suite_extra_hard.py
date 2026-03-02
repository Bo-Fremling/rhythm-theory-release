#!/usr/bin/env python3
"""Run Core no-facit suite twice: normal + overlay-absent (extra-hard).

Why
- `run_core_no_facit_suite.py` already stubs overlay during each coregen run.
- This tool adds a stronger check: Core must also PASS when 00_TOP/OVERLAY is
  physically missing, proving there is no runtime dependency on its presence.

Policy
- Still NO-FACIT: this tool must not run compare.
- It only orchestrates two calls to the existing core suite runner.

Writes
- out/CORE_AUDIT/core_suite_extra_hard_v0_1_<STAMP>.json
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]


def _latest_new(before: set[str], pattern: str) -> Optional[Path]:
    after = {str(p) for p in (REPO / "out" / "CORE_AUDIT").glob(pattern)}
    new = sorted(after - before)
    return Path(new[-1]) if new else None


def _run_suite() -> tuple[int, Optional[Path]]:
    out_dir = REPO / "out" / "CORE_AUDIT"
    out_dir.mkdir(parents=True, exist_ok=True)

    before = {str(p) for p in out_dir.glob("core_suite_run_v0_1_*.json")}
    rc = subprocess.call(["python3", str(REPO / "00_TOP" / "TOOLS" / "run_core_no_facit_suite.py")])
    log = _latest_new(before, "core_suite_run_v0_1_*.json")
    return int(rc), log


def main() -> int:
    out_dir = REPO / "out" / "CORE_AUDIT"
    out_dir.mkdir(parents=True, exist_ok=True)

    overlay = REPO / "00_TOP" / "OVERLAY"
    moved = None

    # Pass A: normal
    rc_a, log_a = _run_suite()

    # Pass B: overlay physically absent
    if overlay.exists():
        moved = REPO / "00_TOP" / "OVERLAY__OFF_FOR_EXTRA_HARD"
        if moved.exists():
            i = 1
            while True:
                cand = REPO / "00_TOP" / f"OVERLAY__OFF_FOR_EXTRA_HARD__ALT{i}"
                if not cand.exists():
                    moved = cand
                    break
                i += 1
        overlay.rename(moved)

    try:
        rc_b, log_b = _run_suite()
    finally:
        if moved is not None:
            try:
                moved.rename(overlay)
            except Exception:
                pass

    # Summarize counts
    def _counts(p: Optional[Path]) -> Optional[dict]:
        if p is None or not p.exists():
            return None
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            return j.get("counts")
        except Exception:
            return None

    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    summary = {
        "version": "v0_1",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        # __file__ may be relative depending on how the script is invoked.
        # Resolve to an absolute path before computing a repo-relative runner path.
        "runner": str(Path(__file__).resolve().relative_to(REPO)).replace("\\", "/"),
        "passes": {
            "A_normal": {"exit": rc_a, "log": (str(log_a.relative_to(REPO)).replace("\\", "/") if log_a else None), "counts": _counts(log_a)},
            "B_overlay_missing": {"exit": rc_b, "log": (str(log_b.relative_to(REPO)).replace("\\", "/") if log_b else None), "counts": _counts(log_b)},
        },
    }

    jp = out_dir / f"core_suite_extra_hard_v0_1_{stamp}.json"
    jp.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {jp}")

    return 0 if (rc_a == 0 and rc_b == 0) else 2


if __name__ == "__main__":
    raise SystemExit(main())
