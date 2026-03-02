#!/usr/bin/env python3
"""EW_COUPLING_LOCK verifier (v0.1)

Checks the deterministic EW tree-level coupling artifact produced by:
  00_TOP/LOCKS/EW_COUPLING_LOCK/ew_coupling_lock_run.py

Policy:
  - Overlay-only numeric check.
  - No running.
  - Includes one NEG control: using an SM-like running sin^2(theta_W) must *not*
    satisfy the RT LO ratio g'/g = 1/sqrt(3).

Usage (repo root):
  python3 00_TOP/LOCKS/EW_COUPLING_LOCK/ew_coupling_lock_verify.py

Outputs:
  out/EW_COUPLING_LOCK/ew_coupling_lock_verify_v0_1.json
  out/EW_COUPLING_LOCK/ew_coupling_lock_verify_summary_v0_1.md
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict

VERSION = "v0_1"


def _repo_root_from_here(here: Path) -> Path:
    return here.resolve().parents[3]


def _read_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: Path, obj: Dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def main() -> int:
    repo = _repo_root_from_here(Path(__file__))
    in_json = repo / "out/EW_COUPLING_LOCK/ew_coupling_lock_v0_1.json"
    out_json = repo / f"out/EW_COUPLING_LOCK/ew_coupling_lock_verify_{VERSION}.json"
    out_md = repo / f"out/EW_COUPLING_LOCK/ew_coupling_lock_verify_summary_{VERSION}.md"

    if not in_json.exists():
        obj = {
            "version": VERSION,
            "inputs": {"ew_coupling_lock": str(in_json.relative_to(repo))},
            "gate": {"PASS": False, "reason": "missing_input"},
            "checks": {},
        }
        _write_json(out_json, obj)
        _write_text(out_md, "# EW_COUPLING_LOCK verify (v0.1)\n\nMISSING input.\n")
        return 2

    ew = _read_json(in_json)
    ratio = float(((ew.get("result") or {}).get("gprime_over_g")))

    target = 1.0 / math.sqrt(3.0)
    tol_abs = 1e-12
    check_ratio = abs(ratio - target) <= tol_abs

    # NEG: typical SM running value sin^2(theta_W)~0.23122 => tan(theta_W) != 1/sqrt(3)
    sin2_running = 0.23122
    tan_running = math.sqrt(sin2_running / (1.0 - sin2_running))
    neg_margin = 1e-3
    neg_pass = abs(tan_running - target) > neg_margin

    checks = {
        "input_gate_pass": bool((ew.get("gate") or {}).get("pass", False)),
        "ratio_is_1_over_sqrt3": {
            "pass": bool(check_ratio),
            "rt_ratio": ratio,
            "target": target,
            "tol_abs": tol_abs,
        },
        "NEG_sm_running_sin2_fails_LO_ratio": {
            "pass": bool(neg_pass),
            "sin2": sin2_running,
            "tan_thetaW": tan_running,
            "target": target,
            "margin_abs": neg_margin,
            "note": "NEG should differ from 1/sqrt(3); Overlay-only sanity.",
        },
    }

    gate_pass = bool(
        checks["input_gate_pass"]
        and checks["ratio_is_1_over_sqrt3"]["pass"]
        and checks["NEG_sm_running_sin2_fails_LO_ratio"]["pass"]
    )

    obj = {
        "version": VERSION,
        "inputs": {"ew_coupling_lock": str(in_json.relative_to(repo))},
        "checks": checks,
        "gate": {
            "PASS": gate_pass,
            "components": {
                "input_gate_pass": bool(checks["input_gate_pass"]),
                "ratio_is_1_over_sqrt3": bool(checks["ratio_is_1_over_sqrt3"]["pass"]),
                "NEG_sm_running_sin2_fails_LO_ratio": bool(checks["NEG_sm_running_sin2_fails_LO_ratio"]["pass"]),
            },
        },
        "policy": {
            "scope": "overlay_numeric",
            "no_running": True,
            "no_new_continuous_params": True,
        },
    }

    _write_json(out_json, obj)

    md = []
    md.append("# EW_COUPLING_LOCK verify (v0.1)\n")
    md.append(f"\nOverall: **{'PASS' if gate_pass else 'FAIL'}**\n")
    md.append("\n## Checks\n")
    md.append(f"- input_gate_pass: {'PASS' if checks['input_gate_pass'] else 'FAIL'}\n")
    rchk = checks["ratio_is_1_over_sqrt3"]
    md.append(
        f"- ratio_is_1_over_sqrt3: {'PASS' if rchk['pass'] else 'FAIL'} (rt={rchk['rt_ratio']}, target={rchk['target']}, tol_abs={rchk['tol_abs']})\n"
    )
    nchk = checks["NEG_sm_running_sin2_fails_LO_ratio"]
    md.append(
        f"- NEG_sm_running_sin2_fails_LO_ratio: {'PASS' if nchk['pass'] else 'FAIL'} (sin2={nchk['sin2']}, tan={nchk['tan_thetaW']}, target={nchk['target']}, margin_abs={nchk['margin_abs']})\n"
    )
    md.append("\nPolicy: Overlay-only numeric; no running; NEG is a sanity contrast.\n")
    _write_text(out_md, "".join(md))

    return 0 if gate_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
