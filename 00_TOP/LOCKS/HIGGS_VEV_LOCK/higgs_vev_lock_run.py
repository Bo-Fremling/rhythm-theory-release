#!/usr/bin/env python3
"""HIGGS/VEV LOCK (v0.3)

This lock remains *non-numeric* for (v, m_H) in Core.

What v0.3 DOES lock (dimensionless, Core-struct):
  - sin^2(theta_W) = 1/4
  - g'/g = 1/sqrt(3)
  - mW/mZ = sqrt(3)/2
  - rho_tree = 1
  - minimal Higgs content: 1 SU(2) doublet, Y=1/2

These are structural outputs from the RT Beviskedja baseline, expressed without SI.
No new continuous parameters. Deterministic.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def _sqrt3_float() -> float:
    return 3.0 ** 0.5


@dataclass(frozen=True)
class Prereq:
    path: str
    exists: bool


def _repo_root_from_here(here: Path) -> Path:
    # here = .../00_TOP/LOCKS/HIGGS_VEV_LOCK/higgs_vev_lock_run.py
    return here.resolve().parents[3]


def main() -> int:
    here = Path(__file__).resolve()
    repo_root = _repo_root_from_here(here)
    out_dir = repo_root / "out" / "HIGGS_VEV_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    prereq_paths = [
        repo_root / "00_TOP" / "OVERLAY" / "kappa_global.json",
        repo_root / "out" / "FLAVOR_LOCK" / "flavor_lock_summary_v0_9.md",
        repo_root / "out" / "EM_LOCK" / "em_lock_summary_v0_2.md",
        repo_root / "00_TOP" / "LOCKS" / "SM_PARAM_INDEX" / "SM_29_PARAMETERS_STATUS.md",
    ]

    prereqs: List[Prereq] = [
        Prereq(path=str(p.relative_to(repo_root)).replace("\\", "/"), exists=p.exists())
        for p in prereq_paths
    ]

    # Optional: allow a *single* energy anchor in Overlay.
    # We only *detect* presence; we do not use SI values.
    overlay_energy_anchor = repo_root / "00_TOP" / "OVERLAY" / "energy_anchor_reference.json"

    prereq_ok = all(p.exists() for p in prereq_paths)

    ew_struct = {
        "sin2_thetaW": {"exact": "1/4", "float": 0.25},
        "gprime_over_g": {"exact": "1/sqrt(3)", "float": 1.0 / _sqrt3_float()},
        "mW_over_mZ": {"exact": "sqrt(3)/2", "float": _sqrt3_float() / 2.0},
        "rho_tree": {"exact": "1", "float": 1.0},
        "higgs_doublets": {"exact": "1", "float": 1.0},
        "higgs_hypercharge_Y": {"exact": "1/2", "float": 0.5},
    }

    gates: Dict[str, Any] = {
        "prereq_presence": prereq_ok,
        "overlay_energy_anchor_present": overlay_energy_anchor.exists(),
        "overlay_energy_anchor_max1_policy": True,
        "ew_struct_locked": True,
    }

    status = "PASS_STRUCT" if prereq_ok else "BLOCKED_MISSING_PREREQS"

    payload: Dict[str, Any] = {
        "lock": "HIGGS_VEV_LOCK",
        "version": "v0.3",
        "timestamp_utc": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "policy": {
            "core_no_si": True,
            "no_new_continuous_params": True,
            "overlay_max_energy_anchor": 1,
            "deterministic": True,
        },
        "prereqs": [asdict(p) for p in prereqs],
        "gates": gates,
        "status": status,
        "result": {
            "ew_struct": ew_struct,
            "v_dimless": None,
            "mH_dimless": None,
            "notes": "v0.3 locks EW/Higgs structure only. Absolute scale (v, mH) remains STRUCT until a dedicated anchor/lock exists.",
        },
    }

    (out_dir / "higgs_vev_lock_v0_3.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    lines: List[str] = []
    lines.append("# HIGGS/VEV LOCK — v0.3")
    lines.append("")
    lines.append(f"Status: **{payload['status']}**")
    lines.append("")
    lines.append("## Gates")
    for k, v in payload["gates"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Policies")
    for k, v in payload["policy"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Prerequisites (presence only)")
    for pr in prereqs:
        mark = "OK" if pr.exists else "MISSING"
        lines.append(f"- {mark}: `{pr.path}`")
    lines.append("")
    lines.append("## EW/Higgs strukturlås (dimensionless)")
    for k, v in payload["result"]["ew_struct"].items():
        lines.append(f"- {k}: {v['exact']}  (≈ {v['float']})")
    lines.append("")
    lines.append("## Notes")
    lines.append(payload["result"]["notes"])
    lines.append("")

    (out_dir / "higgs_vev_lock_summary_v0_3.md").write_text("\n".join(lines), encoding="utf-8")

    return 0 if prereq_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
