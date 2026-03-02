#!/usr/bin/env python3
"""EM_LOCK v0.2 runner (Overlay-only numeric, Core-structure spec).

v0.2 adds:
  - multi-route reporting for Xi_RT (=2alpha)
  - a mutual-consistency gate when both alpha_ref and Z0_ref exist

Identities used:
  R_K := h/e^2
  G0  := e^2/h

  alpha = Z0/(2 R_K)
  Xi_RT := 2 alpha = Z0/R_K = Z0*G0

Inputs (Overlay refs):
  00_TOP/OVERLAY/alpha_reference.json (optional but recommended)
  00_TOP/OVERLAY/z0_reference.json    (optional but recommended)

Outputs:
  out/EM_LOCK/em_lock_v0_2.json
  out/EM_LOCK/em_lock_summary_v0_2.md

Policy:
  - Overlay-only numeric. This does NOT claim alpha is derived from Core yet.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional


VERSION = "em_lock_v0_2"


def _repo_root_from_here(here: Path) -> Path:
    # here = .../00_TOP/LOCKS/EM_LOCK/em_lock_run.py
    return here.resolve().parents[3]


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def ppb(delta_rel: Optional[float]) -> Optional[float]:
    if delta_rel is None:
        return None
    return delta_rel * 1e9


def main() -> int:
    root = _repo_root_from_here(Path(__file__))
    overlay_dir = root / "00_TOP" / "OVERLAY"
    out_dir = root / "out" / "EM_LOCK"

    alpha_ref_j = _load_json(overlay_dir / "alpha_reference.json") or {}
    z0_ref_j = _load_json(overlay_dir / "z0_reference.json") or {}

    alpha_ref = alpha_ref_j.get("alpha")
    z0_ref = z0_ref_j.get("Z0_ohm")
    z0_unc = z0_ref_j.get("Z0_unc_ohm")

    # 2019-SI: h and e are exact by definition.
    # We keep them explicit here to avoid external dependencies.
    h = 6.62607015e-34
    e = 1.602176634e-19

    R_K = h / (e * e)    # von Klitzing (Ohm)
    G0 = (e * e) / h    # e^2/h (Siemens)

    # Multi-route quantities
    xi_from_z0_rk = (z0_ref / R_K) if (z0_ref is not None) else None
    xi_from_z0_g0 = (z0_ref * G0) if (z0_ref is not None) else None
    alpha_from_z0 = (z0_ref / (2.0 * R_K)) if (z0_ref is not None) else None

    # Reverse route: infer Z0 from alpha
    z0_from_alpha = (2.0 * alpha_ref * R_K) if (alpha_ref is not None) else None

    delta_alpha_rel = None
    if (alpha_ref is not None) and (alpha_from_z0 is not None) and alpha_ref != 0:
        delta_alpha_rel = (alpha_from_z0 / alpha_ref) - 1.0

    delta_z0_rel = None
    if (z0_ref is not None) and (z0_from_alpha is not None) and z0_ref != 0:
        delta_z0_rel = (z0_from_alpha / z0_ref) - 1.0

    # Simple gate: if both refs exist, require mutual consistency within tolerance.
    gate_ppb = 50.0
    gate_pass = None
    if delta_z0_rel is not None:
        gate_pass = abs(ppb(delta_z0_rel)) <= gate_ppb

    out_json = {
        "version": VERSION,
        "date": str(date.today()),
        "inputs": {
            "alpha_ref": alpha_ref,
            "z0_ref_ohm": z0_ref,
            "z0_unc_ohm": z0_unc,
            "alpha_ref_source": alpha_ref_j.get("source"),
            "z0_ref_source": z0_ref_j.get("source"),
        },
        "constants_exact": {
            "h_Js": h,
            "e_C": e,
            "R_K_ohm": R_K,
            "G0_S": G0,
        },
        "routes": {
            "xi_from_z0_over_rk": xi_from_z0_rk,
            "xi_from_z0_times_g0": xi_from_z0_g0,
            "alpha_from_z0_over_2rk": alpha_from_z0,
            "z0_from_alpha_times_2rk": z0_from_alpha,
        },
        "deltas": {
            "delta_rel_alpha_from_z0_vs_alpha_ref": delta_alpha_rel,
            "delta_ppb_alpha_from_z0_vs_alpha_ref": ppb(delta_alpha_rel),
            "delta_rel_z0_from_alpha_vs_z0_ref": delta_z0_rel,
            "delta_ppb_z0_from_alpha_vs_z0_ref": ppb(delta_z0_rel),
        },
        "gate": {
            "gate_ppb": gate_ppb,
            "pass": gate_pass,
            "note": "Gate only applies when both alpha_ref and z0_ref exist.",
        },
        "policy": {
            "scope": "OVERLAY_ONLY",
            "core_claim": "Structure identities locked; numeric Core-derivation pending.",
        },
    }

    # Write outputs
    _write_json(out_dir / "em_lock_v0_2.json", out_json)

    lines = []
    lines.append(f"# EM_LOCK v0.2 summary ({out_json['date']})")
    lines.append("")
    lines.append("## Inputs")
    lines.append(f"- alpha_ref: {alpha_ref}")
    lines.append(f"- Z0_ref (Ohm): {z0_ref} (unc={z0_unc})")
    lines.append("")
    lines.append("## Multi-route")
    lines.append(f"- Xi = Z0/R_K: {xi_from_z0_rk}")
    lines.append(f"- Xi = Z0*(e^2/h): {xi_from_z0_g0}")
    lines.append(f"- alpha = Z0/(2 R_K): {alpha_from_z0}")
    lines.append(f"- Z0 = 2 alpha R_K (from alpha_ref): {z0_from_alpha}")
    lines.append("")
    lines.append("## Consistency")
    if delta_alpha_rel is not None:
        lines.append(f"- delta(alpha_from_z0 vs alpha_ref): {ppb(delta_alpha_rel):.3f} ppb")
    else:
        lines.append("- delta(alpha_from_z0 vs alpha_ref): N/A")

    if delta_z0_rel is not None:
        lines.append(f"- delta(Z0_from_alpha vs Z0_ref): {ppb(delta_z0_rel):.3f} ppb")
        lines.append(f"- gate: {'PASS' if gate_pass else 'FAIL'} (|delta| <= {gate_ppb} ppb)")
    else:
        lines.append("- delta(Z0_from_alpha vs Z0_ref): N/A")
        lines.append("- gate: N/A")

    lines.append("")
    lines.append("## Policy")
    lines.append("Overlay-only numeric. Core-level Xi_RT derivation is TODO.")
    lines.append("")

    _write_text(out_dir / "em_lock_summary_v0_2.md", "\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
