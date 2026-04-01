#!/usr/bin/env python3
"""FLAVOR_LOCK coregen (NO-FACIT) — release patch variant.

Genererar deterministiska kandidater och skriver ENDAST till out/CORE_FLAVOR_LOCK/.

WHY THIS VARIANT EXISTS
- The older HARD FAIL on --full was introduced as a practical workaround for a
  constrained execution environment.
- On a normal laptop, full scan is feasible.
- The reduced scan can distort the flavor outcome, especially in the up/down sector.

POLICY IN THIS VARIANT
- Full scan is allowed.
- Full scan is the default.
- A smaller scan remains available via --no-full for debugging or constrained runs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from flavor_lock_run import (
    ensure_dir,
    make_summary,
    repo_root_from_here,
    run_enu,
    run_ud,
    write_json,
    write_text,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=32, help="keep top-N per sector before pairing")
    ap.add_argument("--seed", type=int, default=1337, help="deterministic tie-break seed")
    ap.add_argument("--full", dest="full", action="store_true", help="larger scan (default)")
    ap.add_argument("--no-full", dest="full", action="store_false", help="smaller scan")
    ap.set_defaults(full=True)
    args = ap.parse_args()

    repo = repo_root_from_here(Path(__file__))
    out = repo / "out" / "CORE_FLAVOR_LOCK"
    ensure_dir(out)

    ud_path = out / "flavor_ud_core_v0_9.json"
    enu_path = out / "flavor_enu_core_v0_9.json"
    sum_path = out / "flavor_lock_core_summary_v0_9.md"

    # Fast path: reuse artefacts only if they match the requested (top, seed, full).
    def _load(p: Path) -> dict:
        return json.loads(p.read_text(encoding="utf-8"))

    if ud_path.exists() and enu_path.exists():
        try:
            ud0 = _load(ud_path)
            enu0 = _load(enu_path)
            requested_full = bool(args.full)
            ok_ud = (
                ud0.get("version") == "v0.9"
                and bool((ud0.get("scan") or {}).get("full")) is requested_full
                and int((ud0.get("scan") or {}).get("top")) == int(args.top)
                and int((ud0.get("scan") or {}).get("seed")) == int(args.seed)
                and (ud0.get("scan") or {}).get("tiebreak") == "cost_then_choice_lex_v0_1"
            )
            ok_enu = (
                enu0.get("version") == "v0.9"
                and bool((enu0.get("scan") or {}).get("full")) is requested_full
                and int((enu0.get("scan") or {}).get("top")) == int(args.top)
                and int((enu0.get("scan") or {}).get("seed")) == int(args.seed)
                and (enu0.get("scan") or {}).get("tiebreak") == "cost_then_choice_lex_v0_1"
            )
            if ok_ud and ok_enu:
                summary = make_summary(ud0, enu0).replace("out/FLAVOR_LOCK", "out/CORE_FLAVOR_LOCK")
                write_text(sum_path, summary)
                print(f"REUSED: {out}")
                return 0
        except Exception:
            pass

    ud = run_ud(full=args.full, top=args.top, seed=args.seed)
    enu = run_enu(
        full=args.full,
        top=args.top,
        seed=args.seed,
        avoid_d_ratios=(ud["d"]["ratios"]["m1_over_m2"], ud["d"]["ratios"]["m2_over_m3"]),
    )
    summary = make_summary(ud, enu).replace("out/FLAVOR_LOCK", "out/CORE_FLAVOR_LOCK")

    write_json(ud_path, ud)
    write_json(enu_path, enu)
    write_text(sum_path, summary)

    print(f"WROTE: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
