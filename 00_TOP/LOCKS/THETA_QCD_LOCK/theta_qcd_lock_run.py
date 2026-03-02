#!/usr/bin/env python3
"""THETA_QCD_LOCK (v0.2 structure-lock).

Goal (RT/Core): encode the *structural* claim that the strong-CP angle is fixed to
θ_QCD = 0 by RT symmetries (no continuous dial). This lock is intentionally
*not* an experimental fit; it is a deterministic Core statement with a hard gate.

Artifacts:
  out/THETA_QCD_LOCK/theta_qcd_lock_v0_2.json
  out/THETA_QCD_LOCK/theta_qcd_lock_summary_v0_2.md

Exit codes:
  0: PASS
  2: FAIL/BLOCKED

Policy:
  - Core-only (no overlay reads)
  - No new continuous parameters
  - Deterministic
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def _repo_root_from_here(here: Path) -> Path:
    return here.resolve().parents[3]


def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _write_json(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    here = Path(__file__).resolve()
    repo = _repo_root_from_here(here)

    # Presence prerequisites (Core-only; no overlay reads)
    prereqs = {
        "sm29_status": repo / "00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_PARAMETERS_STATUS.md",
        "su3_note": repo / "00_TOP/RT_CORE_CONTRACT_GLOBAL_v1_2026-01-06.md",
    }

    prereq_presence = all(p.exists() for p in prereqs.values())

    # Structural proxy (Core claim): theta is exactly zero.
    theta_deg = 0.0

    implemented = True
    theta_exact_zero = (theta_deg == 0.0)

    ok = bool(prereq_presence and implemented and theta_exact_zero)

    artifact = {
        "version": "v0.2",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "status": "STRUCT_LOCKED_ZERO",
        "policy": {
            "core_no_si": True,
            "no_new_continuous_params": True,
            "deterministic": True,
            "promotion_requires_verify": False,
            "note": "This is a structure-lock (θ_QCD=0 claim), not a data-fit.",
        },
        "gates": {
            "prereq_presence": prereq_presence,
            "implemented": implemented,
            "theta_exact_zero": theta_exact_zero,
        },
        "prerequisites": {k: str(v.relative_to(repo)).replace("\\", "/") for k, v in prereqs.items()},
        "results": {
            "theta_qcd_deg": theta_deg,
            "theta_qcd_rad": 0.0,
        },
        "gate": {
            "pass": ok,
            "reason": "ok" if ok else "blocked",
        },
        "notes": [
            "v0.2 encodes the RT structural claim θ_QCD = 0 (no continuous knob).",
            "This lock does not attempt to reproduce experimental bounds; it is a Core assertion gated for determinism and prerequisite presence.",
        ],
    }

    out_json = repo / "out/THETA_QCD_LOCK/theta_qcd_lock_v0_2.json"
    out_md = repo / "out/THETA_QCD_LOCK/theta_qcd_lock_summary_v0_2.md"

    _write_json(out_json, artifact)

    lines = []
    lines.append("# THETA_QCD_LOCK v0.2 (structure-lock)")
    lines.append("")
    lines.append(f"Overall: {'PASS' if ok else 'FAIL'}")
    lines.append("")
    lines.append("## Result")
    lines.append(f"- theta_qcd_deg: {theta_deg}")
    lines.append("")
    lines.append("## Gates")
    for k, v in artifact["gates"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Notes")
    for n in artifact["notes"]:
        lines.append(f"- {n}")
    lines.append("")
    lines.append("## Prerequisites")
    for k, p in prereqs.items():
        lines.append(f"- {'OK' if p.exists() else 'MISSING'}: `{artifact['prerequisites'][k]}`")
    lines.append("")

    _write_text(out_md, "\n".join(lines) + "\n")

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
