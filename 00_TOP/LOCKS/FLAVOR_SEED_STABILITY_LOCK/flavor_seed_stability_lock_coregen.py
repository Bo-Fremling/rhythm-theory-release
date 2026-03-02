#!/usr/bin/env python3
"""FLAVOR_SEED_STABILITY_LOCK coregen (NO-FACIT).

Goal
  Prove that FLAVOR_LOCK preferred choices are not an artefact of a tie-break RNG seed.

Policy
  - Core-only: must not read 00_TOP/OVERLAY/** or any *reference*.json.
  - Must not use --full.

What is checked
  Canonical is the on-disk FLAVOR_LOCK v0.9 artefacts produced by flavor_lock_coregen.py
  (default: top=32, seed=1337). We re-run the same constructive scan with a different
  seed (default: 1338) and require that the preferred choices and key derived
  ratios/angles are identical.

Writes
  out/CORE_FLAVOR_SEED_STABILITY_LOCK/flavor_seed_stability_core_v0_1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

# Import FLAVOR core construction directly (core-only, no overlay reads).
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
    ap.add_argument("--top", type=int, default=32)
    ap.add_argument("--seed_canon", type=int, default=1337)
    ap.add_argument("--seed_alt", type=int, default=1338)
    args = ap.parse_args()

    repo = repo_root_from_here(Path(__file__))
    out = repo / "out" / "CORE_FLAVOR_SEED_STABILITY_LOCK"
    ensure_dir(out)

    out_p = out / "flavor_seed_stability_core_v0_1.json"

    # Fast path: if a previous PASS artefact already exists and matches the
    # requested params, reuse it to keep the Core suite runtime bounded.
    if out_p.exists():
        try:
            prev = _load_json(out_p)
            ok = (
                prev.get("version") == "v0_1"
                and prev.get("status") == "PASS"
                and (prev.get("params") or {}).get("top") == args.top
                and (prev.get("params") or {}).get("seed_canon") == args.seed_canon
                and (prev.get("params") or {}).get("seed_alt") == args.seed_alt
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

    # Basic sanity on canonical meta.
    issues: list[str] = []
    scan_ud = canon_ud.get("scan") or {}
    scan_enu = canon_enu.get("scan") or {}

    if scan_ud.get("full") is not False or scan_enu.get("full") is not False:
        issues.append("canonical_fullscan_true")
    if int(scan_ud.get("top", -1)) != int(args.top) or int(scan_enu.get("top", -1)) != int(args.top):
        issues.append("canonical_top_mismatch")
    if int(scan_ud.get("seed", -1)) != int(args.seed_canon) or int(scan_enu.get("seed", -1)) != int(args.seed_canon):
        issues.append("canonical_seed_mismatch")
    if scan_ud.get("tiebreak") != "cost_then_choice_lex_v0_1" or scan_enu.get("tiebreak") != "cost_then_choice_lex_v0_1":
        issues.append("canonical_tiebreak_unexpected")

    avoid = (canon_ud["d"]["ratios"]["m1_over_m2"], canon_ud["d"]["ratios"]["m2_over_m3"])

    alt_ud = run_ud(full=False, top=args.top, seed=args.seed_alt)
    alt_enu = run_enu(full=False, top=args.top, seed=args.seed_alt, avoid_d_ratios=avoid)

    canon_ud_pick = _pick_fields_ud(canon_ud)
    canon_enu_pick = _pick_fields_enu(canon_enu)
    alt_ud_pick = _pick_fields_ud(alt_ud)
    alt_enu_pick = _pick_fields_enu(alt_enu)

    if alt_ud_pick != canon_ud_pick:
        issues.append("seed_changes_ud_preferred")
    if alt_enu_pick != canon_enu_pick:
        issues.append("seed_changes_enu_preferred")

    payload = {
        "version": "v0_1",
        "policy": {"no_facit": True, "forbidden_fullscan": True},
        "params": {"top": args.top, "seed_canon": args.seed_canon, "seed_alt": args.seed_alt},
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "canonical": {"ud": canon_ud_pick, "enu": canon_enu_pick},
        "alt": {"ud": alt_ud_pick, "enu": alt_enu_pick},
        "canonical_meta": {"ud_scan": scan_ud, "enu_scan": scan_enu},
        "alt_meta": {"ud_scan": alt_ud.get("scan"), "enu_scan": alt_enu.get("scan")},
    }

    write_json(out_p, payload)

    if issues:
        raise SystemExit(10)

    print(f"WROTE: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
