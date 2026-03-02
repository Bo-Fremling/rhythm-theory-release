#!/usr/bin/env python3
"""EM_LOCK verifier (deterministic; overlay consistency only).

Usage (from repo root):
  python3 00_TOP/LOCKS/EM_LOCK/em_lock_verify.py

Inputs:
  out/EM_LOCK/em_lock_v0_2.json
  00_TOP/OVERLAY/alpha_reference.json
  00_TOP/OVERLAY/z0_reference.json

Outputs:
  out/EM_LOCK/em_lock_verify_v0_1.json
  out/EM_LOCK/em_lock_verify_summary_v0_1.md

Exit codes:
  0 PASS, 1 FAIL, 2 MISSING
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[3]

def _load_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))

def main() -> int:
    em_json = REPO_ROOT / "out/EM_LOCK/em_lock_v0_2.json"
    alpha_ref = REPO_ROOT / "00_TOP/OVERLAY/alpha_reference.json"
    z0_ref = REPO_ROOT / "00_TOP/OVERLAY/z0_reference.json"
    out_dir = REPO_ROOT / "out/EM_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    missing = [str(p.relative_to(REPO_ROOT)) for p in (em_json, alpha_ref, z0_ref) if not p.exists()]
    if missing:
        (out_dir / "em_lock_verify_summary_v0_1.md").write_text(
            "# EM_LOCK verify (v0.1)\n\nMISSING inputs:\n- " + "\n- ".join(missing) + "\n",
            encoding="utf-8",
        )
        return 2

    em = _load_json(em_json)
    gate = em.get("gate", {})
    gate_pass = bool(gate.get("pass", gate.get("PASS", False)))

    # Also verify that em.inputs match references (exact float equality not required; use strings from refs as declared inputs)
    a = _load_json(alpha_ref)
    z0 = _load_json(z0_ref)
    # Support either naming convention.
    a_val = a.get("alpha_ref", a.get("alpha"))
    z0_val = z0.get("z0_ref_ohm", z0.get("Z0_ohm"))

    inp = em.get("inputs", {})
    inp_a = inp.get("alpha_ref")
    inp_z0 = inp.get("z0_ref_ohm")

    # Compare numerically (robust to float formatting)
    refs_match = (a_val is not None and z0_val is not None and
                  inp_a is not None and inp_z0 is not None and
                  math.isclose(float(inp_a), float(a_val), rel_tol=0.0, abs_tol=0.0) and
                  math.isclose(float(inp_z0), float(z0_val), rel_tol=0.0, abs_tol=0.0))

    overall = {
        "version": "v0.1",
        "inputs": {
            "em_json": str(em_json.relative_to(REPO_ROOT)),
            "alpha_reference": str(alpha_ref.relative_to(REPO_ROOT)),
            "z0_reference": str(z0_ref.relative_to(REPO_ROOT)),
        },
        "checks": {
            "gate_pass": gate_pass,
            "references_present": True,
            "references_match_inputs": refs_match,
            "inputs_in_em": {"alpha_ref": inp_a, "z0_ref_ohm": inp_z0},
            "refs": {"alpha_ref": a_val, "z0_ref_ohm": z0_val},
        },
        "gate": {
            "PASS": bool(gate_pass and refs_match),
            "components": {"gate_pass": bool(gate_pass), "refs_match_inputs": bool(refs_match)},
        },
        "notes": [
            "Overlay-only consistency check (no Core claim).",
        ],
    }

    (out_dir / "em_lock_verify_v0_1.json").write_text(json.dumps(overall, indent=2, sort_keys=True), encoding="utf-8")

    md = []
    md.append("# EM_LOCK verify (v0.1)\n")
    md.append(f"\n- gate_pass: {'PASS' if gate_pass else 'FAIL'}")
    md.append(f"\n- refs_match_inputs: {'PASS' if refs_match else 'FAIL'}")
    md.append(f"\n\nOverall: {'PASS' if overall['gate']['PASS'] else 'FAIL'}\n")
    (out_dir / "em_lock_verify_summary_v0_1.md").write_text("".join(md), encoding="utf-8")

    return 0 if overall["gate"]["PASS"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
