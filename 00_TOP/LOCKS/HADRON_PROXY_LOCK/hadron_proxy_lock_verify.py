#!/usr/bin/env python3
"""HADRON_PROXY_LOCK verifier (v0.1)

Checks:
  1) Ratios are present and finite.
  2) Consistency against the reference recomputation (tight tolerance).
  3) NEG control must FAIL the consistency check.

Usage:
  python3 00_TOP/LOCKS/HADRON_PROXY_LOCK/hadron_proxy_lock_verify.py

Inputs:
  out/HADRON_PROXY_LOCK/hadron_proxy_lock_v0_1.json
  00_TOP/OVERLAY/hadron_mass_reference_v0_1.json

Outputs:
  out/HADRON_PROXY_LOCK/hadron_proxy_lock_verify_v0_1.json
  out/HADRON_PROXY_LOCK/hadron_proxy_lock_verify_summary_v0_1.md

Exit codes:
  0 PASS, 1 FAIL, 2 MISSING
"""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _recompute_ratios(ref: Dict[str, Any]) -> Dict[str, float]:
    m = ref.get("masses", {})
    mp = float(m["m_p"]["value"])
    return {
        "m_n_over_m_p": float(m["m_n"]["value"]) / mp,
        "m_pi_over_m_p": float(m["m_pi_pm"]["value"]) / mp,
        "m_K_over_m_p": float(m["m_K_pm"]["value"]) / mp,
        "m_rho_over_m_p": float(m["m_rho_770_0"]["value"]) / mp,
    }


def _finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except Exception:
        return False


def _check_close(a: Dict[str, Any], b: Dict[str, float], tol: float = 1e-12) -> Dict[str, bool]:
    out: Dict[str, bool] = {}
    for k in b:
        if k not in a or not _finite(a[k]):
            out[k] = False
            continue
        out[k] = abs(float(a[k]) - float(b[k])) <= tol
    return out


def main() -> int:
    run_json = REPO_ROOT / "out/HADRON_PROXY_LOCK/hadron_proxy_lock_v0_1.json"
    ref_json = REPO_ROOT / "00_TOP/OVERLAY/hadron_mass_reference_v0_1.json"
    run_script = REPO_ROOT / "00_TOP/LOCKS/HADRON_PROXY_LOCK/hadron_proxy_lock_run.py"
    out_dir = REPO_ROOT / "out/HADRON_PROXY_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    missing = [str(p.relative_to(REPO_ROOT)) for p in (run_json, ref_json, run_script) if not p.exists()]
    if missing:
        (out_dir / "hadron_proxy_lock_verify_summary_v0_1.md").write_text(
            "# HADRON_PROXY_LOCK verify (v0.1)\n\nMISSING inputs:\n- " + "\n- ".join(missing) + "\n",
            encoding="utf-8",
        )
        return 2

    ref = _load_json(ref_json)
    expect = _recompute_ratios(ref)

    run = _load_json(run_json)
    ratios = run.get("ratios_to_mp", {})

    finite_ok = all(_finite(ratios.get(k)) for k in expect)
    closeness = _check_close(ratios, expect, tol=1e-12)
    close_ok = all(closeness.values())

    # NEG: generate separate-tag artifact and ensure it FAILs closeness
    neg_json_path = out_dir / "hadron_proxy_lock_v0_1_neg.json"
    try:
        subprocess.run(
            ["python3", str(run_script), "--neg_corrupt", "--tag", "neg"],
            cwd=str(REPO_ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        neg_run = _load_json(neg_json_path)
        neg_ratios = neg_run.get("ratios_to_mp", {})
        neg_close = _check_close(neg_ratios, expect, tol=1e-12)
        neg_should_fail = (not all(neg_close.values()))
    except Exception:
        neg_should_fail = False

    overall_pass = bool(finite_ok and close_ok and neg_should_fail)

    out = {
        "version": "v0.1",
        "inputs": {
            "hadron_proxy_lock": str(run_json.relative_to(REPO_ROOT)),
            "hadron_mass_reference": str(ref_json.relative_to(REPO_ROOT)),
        },
        "checks": {
            "finite": finite_ok,
            "close_to_reference": close_ok,
            "per_ratio_close": closeness,
            "neg_corrupt_fails_close": neg_should_fail,
        },
        "gate": {"PASS": overall_pass},
        "notes": [
            "This gate currently verifies overlay reference integrity only (v0.1).",
            "RT mapping for hadron proxies is tracked separately in SM29_WORKPLAN.",
        ],
    }

    (out_dir / "hadron_proxy_lock_verify_v0_1.json").write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")

    md = []
    md.append("# HADRON_PROXY_LOCK verify (v0.1)\n")
    md.append(f"\n- finite: {'PASS' if finite_ok else 'FAIL'}\n")
    md.append(f"- close_to_reference: {'PASS' if close_ok else 'FAIL'}\n")
    md.append(f"- NEG (--neg_corrupt) must FAIL close: {'PASS' if neg_should_fail else 'FAIL'}\n")
    md.append(f"\nOverall: {'PASS' if overall_pass else 'FAIL'}\n")
    (out_dir / "hadron_proxy_lock_verify_summary_v0_1.md").write_text("".join(md), encoding="utf-8")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
