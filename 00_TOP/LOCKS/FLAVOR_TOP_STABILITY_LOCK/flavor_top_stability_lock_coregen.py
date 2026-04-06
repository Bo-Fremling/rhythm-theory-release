#!/usr/bin/env python3
"""FLAVOR_TOP_STABILITY_LOCK coregen (NO-FACIT).

Goal
  Make the FLAVOR preferred choice more *structurally forced* by requiring
  stability under a reduced top-N prefilter.

Policy
  - Core-only: must not read 00_TOP/OVERLAY/** or any *reference*.json.
  - Full scan is allowed and is the default canonical mode in this branch.

What is checked
  Canonical is FLAVOR_LOCK v0.9 artefacts produced by flavor_lock_coregen.py
  (default: top=32, seed=1337). We re-run the same constructive scan with a
  smaller top (default: 16) and require that the preferred choices and the
  key derived ratios/angles are identical.

  NOTE: To keep the Core suite runtime bounded, we do NOT re-run the canonical
  scan here. Instead we:
    (1) load canonical artefacts (on-disk),
    (2) compute the top_small run,
    (3) require exact equality of the picked invariants.

Writes
  out/CORE_FLAVOR_TOP_STABILITY_LOCK/flavor_top_stability_core_v0_1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

FL_DIR = REPO / "00_TOP" / "LOCKS" / "FLAVOR_LOCK"
if str(FL_DIR) not in sys.path:
    sys.path.insert(0, str(FL_DIR))

from flavor_lock_run import ensure_dir, repo_root_from_here, run_enu, run_ud, write_json  # type: ignore


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _pick_fields_ud(obj: dict) -> dict:
    return {
        "u_choice": obj["u"]["choice"],
        "d_choice": obj["d"]["choice"],
        "u_ratios": obj["u"]["ratios"],
        "d_ratios": obj["d"]["ratios"],
        "ckm_angles": obj["CKM"]["angles"],
    }


def _pick_fields_enu(obj: dict) -> dict:
    return {
        "e_choice": obj["e"]["choice"],
        "nu_choice_dirac": obj["nu"]["choice_dirac"],
        "e_ratios": obj["e"]["ratios"],
        "nu_ratios": obj["nu"]["ratios"],
        "pmns_angles": obj["PMNS"]["angles"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", dest="full", action="store_true", help="larger scan (default)")
    ap.add_argument("--no-full", dest="full", action="store_false", help="smaller scan")
    ap.set_defaults(full=True)
    ap.add_argument("--top_small", type=int, default=16)
    ap.add_argument("--top_canon", type=int, default=32)
    ap.add_argument("--seed", type=int, default=1337)
    args = ap.parse_args()

    repo = repo_root_from_here(Path(__file__))
    out = repo / "out" / "CORE_FLAVOR_TOP_STABILITY_LOCK"
    ensure_dir(out)

    out_p = out / "flavor_top_stability_core_v0_1.json"

    if out_p.exists():
        try:
            prev = _load_json(out_p)
            ok = (
                prev.get("version") == "v0_1"
                and prev.get("status") == "PASS"
                and (prev.get("params") or {}).get("top_small") == args.top_small
                and (prev.get("params") or {}).get("top_canon") == args.top_canon
                and (prev.get("params") or {}).get("seed") == args.seed
                and bool((prev.get("params") or {}).get("full")) is bool(args.full)
            )
            if ok:
                print(f"REUSED: {out}")
                return 0
        except Exception:
            pass

    canon_dir = repo / "out" / "CORE_FLAVOR_LOCK"
    canon_ud_p = canon_dir / "flavor_ud_core_v0_9.json"
    canon_enu_p = canon_dir / "flavor_enu_core_v0_9.json"
    if not canon_ud_p.exists() or not canon_enu_p.exists():
        raise SystemExit("HARD FAIL: missing canonical out/CORE_FLAVOR_LOCK artefacts")

    canon_ud = _load_json(canon_ud_p)
    canon_enu = _load_json(canon_enu_p)

    issues: list[str] = []
    scan_ud = canon_ud.get("scan") or {}
    scan_enu = canon_enu.get("scan") or {}
    requested_full = bool(args.full)

    if bool(scan_ud.get("full")) is not requested_full or bool(scan_enu.get("full")) is not requested_full:
        issues.append("canonical_full_mismatch")
    if int(scan_ud.get("top", -1)) != int(args.top_canon) or int(scan_enu.get("top", -1)) != int(args.top_canon):
        issues.append("canonical_top_mismatch")
    if int(scan_ud.get("seed", -1)) != int(args.seed) or int(scan_enu.get("seed", -1)) != int(args.seed):
        issues.append("canonical_seed_mismatch")
    if scan_ud.get("tiebreak") != "cost_then_choice_lex_v0_1" or scan_enu.get("tiebreak") != "cost_then_choice_lex_v0_1":
        issues.append("canonical_tiebreak_unexpected")

    avoid = (canon_ud["d"]["ratios"]["m1_over_m2"], canon_ud["d"]["ratios"]["m2_over_m3"])

    small_ud = run_ud(full=args.full, top=args.top_small, seed=args.seed)
    small_enu = run_enu(full=args.full, top=args.top_small, seed=args.seed, avoid_d_ratios=avoid)

    canon_ud_pick = _pick_fields_ud(canon_ud)
    canon_enu_pick = _pick_fields_enu(canon_enu)
    small_ud_pick = _pick_fields_ud(small_ud)
    small_enu_pick = _pick_fields_enu(small_enu)

    if small_ud_pick != canon_ud_pick:
        issues.append("top_small_changes_ud_preferred")
    if small_enu_pick != canon_enu_pick:
        issues.append("top_small_changes_enu_preferred")

    payload = {
        "version": "v0_1",
        "policy": {"no_facit": True, "fullscan_allowed": True},
        "params": {
            "top_small": args.top_small,
            "top_canon": args.top_canon,
            "seed": args.seed,
            "full": bool(args.full),
        },
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "canonical": {"ud": canon_ud_pick, "enu": canon_enu_pick},
        "small": {"ud": small_ud_pick, "enu": small_enu_pick},
        "canonical_meta": {"ud_scan": canon_ud.get("scan"), "enu_scan": canon_enu.get("scan")},
    }

    write_json(out_p, payload)

    if issues:
        raise SystemExit(10)

    print(f"WROTE: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
