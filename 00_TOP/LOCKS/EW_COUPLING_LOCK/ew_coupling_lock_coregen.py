#!/usr/bin/env python3
"""EW_COUPLING_LOCK coregen (NO-FACIT).

Core-only predictions from RT measure/projector arguments.

Rules
- No α/Z0/PDG/CODATA refs are read.
- This lock MAY read Core artifacts from other locks (e.g. out/CORE_EM_LOCK/*) because
  those are Core-generated and carry no facit influence.

Outputs:
  out/CORE_EW_COUPLING_LOCK/ew_coupling_core_v0_2.json
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[3]


def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _pick_latest(out_dir: Path, pattern: str) -> Optional[Path]:
    cands = sorted(out_dir.glob(pattern))
    return cands[-1] if cands else None


def _load_alpha_candidates(repo: Path) -> tuple[Optional[str], list[dict] | None, Optional[str]]:
    """Load alpha_RT candidates from the latest EM_LOCK Core artifact.

    Returns (artifact_rel_path, candidates_list) where candidates_list is a list of
    dicts with keys {id, expr, approx, source_xi_expr}.
    """
    em_dir = repo / "out" / "CORE_EM_LOCK"
    em = _pick_latest(em_dir, "em_lock_core_v*.json")
    if not em or not em.exists():
        return None, None, None
    obj = _read_json(em)
    cs = obj.get("candidate_space") or {}
    a = cs.get("alpha_RT") if isinstance(cs, dict) else None
    cands = a.get("candidates") if isinstance(a, dict) else None
    pref = None
    if isinstance(a, dict):
        p = a.get("preferred")
        if isinstance(p, dict) and p.get("id"):
            pref = str(p.get("id"))
    if not pref:
        tb = obj.get("tie_break")
        if isinstance(tb, dict):
            pr = tb.get("preferred")
            if isinstance(pr, dict):
                ap = pr.get("alpha_RT")
                if isinstance(ap, dict) and ap.get("id"):
                    pref = str(ap.get("id"))
    if not isinstance(cands, list) or not cands:
        return str(em.relative_to(repo)).replace("\\", "/"), None, pref
    return str(em.relative_to(repo)).replace("\\", "/"), cands, pref


def main() -> int:
    out_dir = REPO / "out" / "CORE_EW_COUPLING_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    sin2 = 1.0 / 4.0
    mw_mz = math.sqrt(3.0) / 2.0

    # Optional: if EM_LOCK provides alpha_RT as a candidate-set, derive g and g' candidate-sets.
    em_art, alpha_cands, alpha_pref_id = _load_alpha_candidates(REPO)
    g_space = None
    if alpha_cands:
        # With sin^2(theta_W)=1/4 => sin(theta_W)=1/2, cos(theta_W)=sqrt(3)/2
        # e := sqrt(4*pi*alpha)
        # g := e/sin = 2e = 4*sqrt(pi*alpha)
        # g' := e/cos = 2e/sqrt(3) = (4/sqrt(3))*sqrt(pi*alpha)
        g_cands = []
        gp_cands = []
        g_pref = None
        gp_pref = None
        for i, c in enumerate(alpha_cands, start=1):
            a_expr = str(c.get("expr"))
            a_val = float(c.get("approx"))
            g_val = 4.0 * math.sqrt(math.pi * a_val)
            gp_val = (4.0 / math.sqrt(3.0)) * math.sqrt(math.pi * a_val)
            g_cands.append({
                "id": f"G{i:03d}",
                "expr": f"4*sqrt(pi*({a_expr}))",
                "approx": g_val,
                "source_alpha_id": c.get("id"),
                "source_alpha_expr": a_expr,
            })
            gp_cands.append({
                "id": f"GP{i:03d}",
                "expr": f"(4/sqrt(3))*sqrt(pi*({a_expr}))",
                "approx": gp_val,
                "source_alpha_id": c.get("id"),
                "source_alpha_expr": a_expr,
            })

            if alpha_pref_id and str(c.get("id")) == str(alpha_pref_id):
                g_pref = {"id": f"G{i:03d}", "expr": f"4*sqrt(pi*({a_expr}))", "approx": g_val}
                gp_pref = {"id": f"GP{i:03d}", "expr": f"(4/sqrt(3))*sqrt(pi*({a_expr}))", "approx": gp_val}

        g_space = {
            "derived_from": "alpha_RT with sin^2(theta_W)=1/4",
            "note": "If alpha_RT is a finite Core candidate-set, then g and g' become finite derived candidate-sets (no facit selection).",
            "g_weak": {
                "type": "derived_candidate_set",
                "relation": "g^2/(4*pi) = alpha_RT/sin^2(theta_W)",
                "with": {"sin2_thetaW": "1/4"},
                "candidates": g_cands,
                "preferred": g_pref,
            },
            "g_hyper": {
                "type": "derived_candidate_set",
                "relation": "g'^2/(4*pi) = alpha_RT/cos^2(theta_W)",
                "with": {"cos2_thetaW": "3/4"},
                "candidates": gp_cands,
                "preferred": gp_pref,
            },
        }

    out = {
        "version": "v0.2",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "core_definition": {
            "ew_struct": "RT-measure projectors -> sin^2(theta_W)=1/4, mW/mZ=sqrt(3)/2",
            "g_relation": "g derived from (alpha_RT, sin^2(theta_W)) if alpha_RT candidate-set exists",
        },
        "inputs": {
            "alpha_source": em_art,
        },
        "predictions": {
            "sin2_thetaW": sin2,
            "mW_over_mZ": mw_mz,
            "R_minus": 1.0 / 4.0,
        },
        "candidate_space": g_space,
        "derivation_status": "DERIVED",
        "validation_status": "UNTESTED",
    }

    p = out_dir / "ew_coupling_core_v0_2.json"
    p.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
