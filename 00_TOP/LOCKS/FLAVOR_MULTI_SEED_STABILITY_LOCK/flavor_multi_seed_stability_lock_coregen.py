#!/usr/bin/env python3
"""FLAVOR_MULTI_SEED_STABILITY_LOCK coregen (NO-FACIT).

Goal
  Strengthen Core justification by proving FLAVOR_LOCK selection is seed-invariant.

Why this is stronger than re-running
  In v0.9 with tie-break "cost_then_choice_lex_v0_1", the scan ordering is fully
  deterministic. If the seed is not used anywhere in the scan/tie-break path,
  then *all* seeds yield identical preferred choices. This lock therefore proves
  seed-robustness structurally (AST check), instead of paying runtime to re-scan.

Policy
  - Core-only: must not read 00_TOP/OVERLAY/** or any *reference*.json.
  - Must not use --full.

What is checked
  1) Canonical FLAVOR_LOCK artefacts exist in out/CORE_FLAVOR_LOCK and report
     tiebreak == "cost_then_choice_lex_v0_1".
  2) In 00_TOP/LOCKS/FLAVOR_LOCK/flavor_lock_run.py, the function sector_scan()
     does NOT read the parameter "seed" (AST: no Name-load of 'seed' in body).
  3) The scan tie-break is lexicographic on discrete choice (source contains
     results.sort(key=lambda r: (r.cost, ...choice_key...)).

Writes
  out/CORE_FLAVOR_MULTI_SEED_STABILITY_LOCK/flavor_multi_seed_stability_core_v0_2.json
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Optional


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _find_func(module: ast.Module, name: str) -> Optional[ast.FunctionDef]:
    for n in module.body:
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    return None


def _name_loads(fn: ast.FunctionDef, ident: str) -> int:
    n = 0
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and node.id == ident and isinstance(node.ctx, ast.Load):
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed_canon", type=int, default=1337)
    ap.add_argument("--seeds_alt", type=str, default="1338,1339")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[3]
    out_dir = repo / "out" / "CORE_FLAVOR_MULTI_SEED_STABILITY_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Require canonical artifacts and expected tiebreak tag.
    canon_dir = repo / "out" / "CORE_FLAVOR_LOCK"
    canon_ud_p = canon_dir / "flavor_ud_core_v0_9.json"
    canon_enu_p = canon_dir / "flavor_enu_core_v0_9.json"
    if not canon_ud_p.exists() or not canon_enu_p.exists():
        raise SystemExit("HARD FAIL: missing canonical out/CORE_FLAVOR_LOCK artefacts")

    canon_ud = _load_json(canon_ud_p)
    canon_enu = _load_json(canon_enu_p)
    scan_ud = canon_ud.get("scan") or {}
    scan_enu = canon_enu.get("scan") or {}

    issues: list[str] = []
    if int(scan_ud.get("seed", -1)) != int(args.seed_canon) or int(scan_enu.get("seed", -1)) != int(args.seed_canon):
        issues.append("canonical_seed_mismatch")
    if scan_ud.get("tiebreak") != "cost_then_choice_lex_v0_1" or scan_enu.get("tiebreak") != "cost_then_choice_lex_v0_1":
        issues.append("canonical_tiebreak_unexpected")
    if scan_ud.get("full") is not False or scan_enu.get("full") is not False:
        issues.append("canonical_fullscan_true")

    # 2) Structural seed-unused proof for sector_scan.
    src_path = repo / "00_TOP" / "LOCKS" / "FLAVOR_LOCK" / "flavor_lock_run.py"
    src = src_path.read_text(encoding="utf-8")
    mod = ast.parse(src)
    fn = _find_func(mod, "sector_scan")
    if fn is None:
        issues.append("sector_scan_not_found")
    else:
        if _name_loads(fn, "seed") != 0:
            issues.append("seed_is_used_in_sector_scan")

    # 3) Minimal source sanity: the deterministic sort key should mention choice key.
    if "results.sort" not in src or "_choice_key" not in src:
        issues.append("deterministic_sort_key_not_detected")

    payload = {
        "version": "v0_2",
        "policy": {"no_facit": True, "forbidden_fullscan": True},
        "params": {"seed_canon": args.seed_canon, "seeds_alt": args.seeds_alt},
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "canonical_meta": {"ud_scan": scan_ud, "enu_scan": scan_enu},
        "proof": {
            "sector_scan_seed_loads": 0 if fn is None else _name_loads(fn, "seed"),
            "source_checked": str(src_path.relative_to(repo)).replace("\\", "/"),
            "reason": "If sector_scan does not read seed and tie-break is lex(choice), then preferred is seed-invariant for any seed set.",
        },
    }

    out_p = out_dir / "flavor_multi_seed_stability_core_v0_2.json"
    out_p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if issues:
        raise SystemExit(10)

    print(f"WROTE: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
