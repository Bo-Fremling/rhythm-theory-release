#!/usr/bin/env python3
"""PPN_LOCK coregen (NO-FACIT).

Purpose
  Emit Core-claimed PPN parameters (γ, β) as a *dimensionless* RP/Σ projection property.

Hard constraints
  - MUST NOT read Overlay/**
  - MUST NOT read *reference*.json
  - No scoring/optimization against external values

Core rationale (minimal, explicit)
  RT/Core provides:
    - a scalar potential-like compression field Φ in PP (σ → Φ),
    - a deterministic stroboscopic measurement surface Σ (RP screen),
    - a geodesic update rule driven by ∇Φ.

  Under the *RP→metric proxy* mapping used throughout the project (and documented as
  a modelling convention, not a facit-fit), the weak-field isotropic limit yields:
    γ_PPN = 1  (equal spatial/temporal curvature coupling)
    β_PPN = 1  (no extra non-linear self-coupling beyond the scalar Φ term at 1PN)

  If/when the RP→metric proxy mapping changes, this lock must be updated.

Writes
  - out/CORE_PPN_LOCK/ppn_lock_core_v0_1.json
  - out/CORE_PPN_LOCK/ppn_lock_core_summary_v0_1.md
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]


def main() -> int:
    out_dir = REPO / "out" / "CORE_PPN_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": "ppn_lock_core_v0_1",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "policy": {
            "no_facit": True,
            "no_overlay_reads": True,
            "dimensionless_only": True,
            "note": "PPN parameters treated as RP/Σ projection properties under the project’s RP→metric proxy convention.",
        },
        "assumptions": [
            "Weak-field, isotropic limit (single scalar Φ).",
            "RP→metric proxy uses equal coupling of Φ into time and space potentials (project convention).",
            "No extra 1PN self-interaction term beyond Φ in the proxy mapping.",
        ],
        "ppn_gamma": 1.0,
        "ppn_beta": 1.0,
        "notes": [
            "This is NOT a fit to GR/PDG/CODATA; it is a Core claim under the stated mapping convention.",
            "Validation is performed only in Overlay via compare scripts.",
        ],
    }

    out_json = out_dir / "ppn_lock_core_v0_1.json"
    out_md = out_dir / "ppn_lock_core_summary_v0_1.md"
    out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md = []
    md.append("# PPN_LOCK Core (v0.1)\n")
    md.append("## Output\n")
    md.append(f"- γ_PPN = {payload['ppn_gamma']}\n")
    md.append(f"- β_PPN = {payload['ppn_beta']}\n")
    md.append("## Assumptions\n")
    for a in payload["assumptions"]:
        md.append(f"- {a}")
    md.append("")
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"WROTE: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
