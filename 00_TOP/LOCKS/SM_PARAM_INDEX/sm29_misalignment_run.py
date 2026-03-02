#!/usr/bin/env python3
"""SM29 misalignment runner (v0.1)

Reads FLAVOR_LOCK verify output and reports a discrete C30 misalignment measure Δk.

Usage:
  python3 00_TOP/LOCKS/SM_PARAM_INDEX/sm29_misalignment_run.py

Inputs:
  out/FLAVOR_LOCK/flavor_lock_verify_v0_1.json

Outputs:
  out/SM29_MISALIGNMENT/sm29_misalignment_v0_1.json
  out/SM29_MISALIGNMENT/sm29_misalignment_summary_v0_1.md

Exit codes:
  0 OK, 2 MISSING
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    inp = REPO_ROOT / "out/FLAVOR_LOCK/flavor_lock_verify_v0_1.json"
    out_dir = REPO_ROOT / "out/SM29_MISALIGNMENT"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not inp.exists():
        (out_dir / "sm29_misalignment_summary_v0_1.md").write_text(
            "# SM29 misalignment (v0.1)\n\nMISSING input:\n- " + str(inp.relative_to(REPO_ROOT)) + "\n",
            encoding="utf-8",
        )
        return 2

    d = _load_json(inp)
    dg = (d.get("checks") or {}).get("delta_grid_C30") or {}

    def get_sector(tag: str) -> Dict[str, Any]:
        sec = dg.get(tag) or {}
        grid = sec.get("C30_grid") or {}
        return {
            "k": grid.get("k"),
            "delta_grid_rad": grid.get("delta_grid_rad"),
            "delta_best_rad": sec.get("delta_best_rad"),
            "delta_best_deg": sec.get("delta_best_deg"),
            "delta_minus_grid_rad": grid.get("delta_minus_grid_rad"),
            "abs_err_grid_max": sec.get("delta_grid_abs_max_err"),
        }

    ckm = get_sector("CKM")
    pmns = get_sector("PMNS")

    k_ckm = ckm.get("k")
    k_pmns = pmns.get("k")

    delta_k = None
    delta_k_mod30 = None
    if isinstance(k_ckm, int) and isinstance(k_pmns, int):
        delta_k = k_pmns - k_ckm
        delta_k_mod30 = (delta_k % 30)

    out = {
        "version": "v0.1",
        "inputs": {
            "flavor_lock_verify": str(inp.relative_to(REPO_ROOT)),
            "misalignment_spec": "00_TOP/LOCKS/SM_PARAM_INDEX/SM29_MISALIGNMENT_SPEC_v0_2.md",
        },
        "C30": {"step_rad": 0.20943951023931953},
        "sectors": {"CKM": ckm, "PMNS": pmns},
        "misalignment": {"delta_k": delta_k, "delta_k_mod30": delta_k_mod30},
        "notes": [
            "Δk is a discrete misalignment indicator derived from C30 projection of δ.",
            "This is a report object; the RT-derivation of k* remains TODO (workplan).",
        ],
    }

    (out_dir / "sm29_misalignment_v0_1.json").write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")

    md = []
    md.append("# SM29 misalignment (v0.1)\n")
    md.append("\n## C30 δ-projection\n")
    md.append(f"- CKM: k={ckm.get('k')}, δ_best={ckm.get('delta_best_deg'):.3f}°\n")
    md.append(f"- PMNS: k={pmns.get('k')}, δ_best={pmns.get('delta_best_deg'):.3f}°\n")
    md.append("\n## Δk\n")
    md.append(f"- Δk = {delta_k} (mod30={delta_k_mod30})\n")
    md.append("\n## Grid forcing error (|M|)\n")
    md.append(f"- CKM abs_err_grid_max = {ckm.get('abs_err_grid_max')}\n")
    md.append(f"- PMNS abs_err_grid_max = {pmns.get('abs_err_grid_max')}\n")
    (out_dir / "sm29_misalignment_summary_v0_1.md").write_text("".join(md), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
