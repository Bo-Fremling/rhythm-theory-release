#!/usr/bin/env python3
"""EW_COUPLING_LOCK v0.1

Derive tree-level electroweak couplings from alpha_ref and RT LO sin^2(theta_W)=1/4.

Policy:
- Overlay numeric only (alpha input).
- No running to m_Z.
- Deterministic, no tuning.

Usage (repo root):
  python3 00_TOP/LOCKS/EW_COUPLING_LOCK/ew_coupling_lock_run.py

Outputs:
  out/EW_COUPLING_LOCK/ew_coupling_lock_v0_1.json
  out/EW_COUPLING_LOCK/ew_coupling_lock_summary_v0_1.md

Exit codes:
  0 = PASS
  2 = FAIL
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Tuple

VERSION = "v0_1"


def _repo_root_from_here(here: Path) -> Path:
    return here.resolve().parents[3]


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _load_json(p: Path) -> dict:
    return json.loads(_read_text(p))


def _write_json(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _finite_pos(x: float) -> bool:
    return (x is not None) and (x > 0.0) and (x == x) and (x != float("inf"))


def _pick_alpha(repo: Path) -> Tuple[bool, str, float, Dict[str, Any]]:
    """Return (ok, source, alpha, extra)."""
    extra: Dict[str, Any] = {}

    em_json = repo / "out/EM_LOCK/em_lock_v0_2.json"
    if em_json.exists():
        try:
            em = _load_json(em_json)
            inp = em.get("inputs", {})
            routes = em.get("routes", {})
            # Prefer alpha_ref if present (explicit reference used by EM_LOCK)
            if "alpha_ref" in inp:
                a = float(inp["alpha_ref"])
                extra["em_lock_path"] = str(em_json.relative_to(repo))
                extra["em_lock_alpha_ref"] = a
                # also record derived alpha if present
                if "alpha_from_z0_over_2rk" in routes:
                    extra["em_lock_alpha_from_z0"] = float(routes["alpha_from_z0_over_2rk"])
                return True, "em_lock.inputs.alpha_ref", a, extra
        except Exception as e:
            extra["em_lock_parse_error"] = str(e)

    # Fallback: overlay reference
    alpha_ref = repo / "00_TOP/OVERLAY/alpha_reference.json"
    if alpha_ref.exists():
        try:
            aobj = _load_json(alpha_ref)
            # allow either {"alpha":...} or {"alpha_ref":...}
            a = aobj.get("alpha", aobj.get("alpha_ref", None))
            a = float(a)
            extra["alpha_reference_path"] = str(alpha_ref.relative_to(repo))
            return True, "overlay.alpha_reference", a, extra
        except Exception as e:
            extra["alpha_reference_parse_error"] = str(e)

    return False, "missing_alpha", float("nan"), extra


def main() -> int:
    here = Path(__file__).resolve()
    repo = _repo_root_from_here(here)

    out_json = repo / f"out/EW_COUPLING_LOCK/ew_coupling_lock_{VERSION}.json"
    out_md = repo / f"out/EW_COUPLING_LOCK/ew_coupling_lock_summary_{VERSION}.md"

    ok, source, alpha, extra = _pick_alpha(repo)
    if not ok or (not _finite_pos(alpha)):
        obj = {
            "version": VERSION,
            "gate": {"pass": False, "reason": "missing_or_invalid_alpha", "source": source},
            "inputs": {"alpha": alpha},
            "extra": extra,
            "policy": {"scope": "overlay_numeric", "running": "none"},
        }
        _write_json(out_json, obj)
        _write_text(out_md, "# EW_COUPLING_LOCK v0.1\n\nFAIL: missing/invalid alpha\n")
        return 2

    # RT LO fixpoint
    sin2 = 0.25
    sin_ = 0.5
    cos_ = math.sqrt(3.0) / 2.0

    e = math.sqrt(4.0 * math.pi * alpha)
    g = e / sin_
    gprime = e / cos_

    obj = {
        "version": VERSION,
        "gate": {"pass": True, "reason": "ok", "alpha_source": source},
        "inputs": {"alpha": alpha},
        "core_assumptions": {
            "sin2_thetaW": {"exact": "1/4", "float": sin2},
        },
        "result": {
            "e": e,
            "g_tree": g,
            "gprime_tree": gprime,
            "gprime_over_g": gprime / g,
        },
        "notes": {
            "meaning": "Tree-level (Q→0) couplings from alpha_ref and sin^2(thetaW)=1/4. No running to mZ.",
        },
        "extra": extra,
        "policy": {
            "scope": "overlay_numeric",
            "running": "none",
            "no_new_continuous_params": True,
            "core_no_si": True,
        },
    }

    _write_json(out_json, obj)

    md = []
    md.append("# EW_COUPLING_LOCK v0.1\n")
    md.append("\nStatus: **PASS**\n")
    md.append("\n## Inputs\n")
    md.append(f"- alpha: {alpha}  (source: {source})\n")
    md.append("\n## Core antagande (LO)\n")
    md.append("- sin^2θ_W = 1/4\n")
    md.append("\n## Resultat (tree-level, ingen running)\n")
    md.append(f"- e = sqrt(4π α) = {e}\n")
    md.append(f"- g = e/sinθ_W = {g}\n")
    md.append(f"- g′ = e/cosθ_W = {gprime}\n")
    md.append(f"- g′/g = {gprime/g}  (förväntat 1/√3 ≈ {1/math.sqrt(3.0)})\n")
    md.append("\n## Policy\n")
    md.append("Overlay-only numeric. Q→0 tree-level kandidatvärde; ingen running till m_Z.\n")

    _write_text(out_md, "".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
