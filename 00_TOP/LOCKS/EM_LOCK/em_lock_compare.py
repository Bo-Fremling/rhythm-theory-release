#!/usr/bin/env python3
"""EM_LOCK compare (Overlay-only; NO FEEDBACK).

Compares Core candidate-set for alpha_RT (derived from Xi_RT/2) against
overlay references.

Rules
- May read 00_TOP/OVERLAY/**
- MUST NOT influence Core generation or candidate ordering.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


REPO = Path(__file__).resolve().parents[3]
LOCK = Path(__file__).resolve().parent.name


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _pick_latest_core() -> Optional[Path]:
    out = REPO / "out" / f"CORE_{LOCK}"
    cands = sorted(out.glob("em_lock_core_v*.json"))
    return cands[-1] if cands else None


def _pick_ref() -> tuple[Optional[Path], Optional[dict]]:
    overlay = REPO / "00_TOP" / "OVERLAY"
    refs = sorted(overlay.glob("sm29_data_reference*.json"))
    if refs:
        r = _load_json(refs[-1]).get("refs", {}).get("alpha")
        return refs[-1], r
    # fallback: alpha_reference.json
    p = overlay / "alpha_reference.json"
    if p.exists():
        j = _load_json(p)
        r = {
            "value": j.get("alpha"),
            "unit": "dimensionless",
            "tol_rel": 1e-8,
            "comment": "fallback from alpha_reference.json",
        }
        return p, r
    return None, None


def main() -> int:
    out_dir = REPO / "out" / f"COMPARE_{LOCK}"
    out_dir.mkdir(parents=True, exist_ok=True)

    core_path = _pick_latest_core()
    ref_path, ref = _pick_ref()

    report = {
        "version": "v0.1",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "lock": LOCK,
        "policy": {"overlay_only": True, "feeds_back": False},
        "inputs": {
            "core": str(core_path.relative_to(REPO)).replace("\\", "/") if core_path else None,
            "ref": str(ref_path.relative_to(REPO)).replace("\\", "/") if ref_path else None,
        },
        "validation_status": "UNTESTED",
        "alpha_compare": None,
    }

    if not core_path or not core_path.exists() or not ref_path or not ref:
        p = out_dir / "em_lock_compare_v0_1.json"
        p.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"WROTE: {p}")
        return 0

    core = _load_json(core_path)
    cs = (core.get("candidate_space") or {}) if isinstance(core, dict) else {}
    a_cs = cs.get("alpha_RT") if isinstance(cs, dict) else None
    a_cands = a_cs.get("candidates") if isinstance(a_cs, dict) else None

    if not isinstance(a_cands, list) or len(a_cands) == 0:
        report["alpha_compare"] = {"status": "MISSING_ALPHA_CANDIDATES"}
        p = out_dir / "em_lock_compare_v0_1.json"
        p.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"WROTE: {p}")
        return 0

    ref_val = float(ref.get("value"))
    tol_rel = float(ref.get("tol_rel", 0.0))

    best = None
    best_rel = None
    hit = None
    for c in a_cands:
        if not isinstance(c, dict):
            continue
        v = c.get("approx")
        try:
            v = float(v)
        except Exception:
            continue
        rel = abs(v - ref_val) / abs(ref_val) if ref_val != 0 else abs(v - ref_val)
        if best_rel is None or rel < best_rel:
            best_rel = rel
            best = {"id": c.get("id"), "expr": c.get("expr"), "value": v}
        if tol_rel and rel <= tol_rel:
            hit = {"id": c.get("id"), "expr": c.get("expr"), "value": v, "rel_err": rel}
            break

    report["alpha_compare"] = {
        "ref": {"value": ref_val, "tol_rel": tol_rel, "unit": ref.get("unit"), "comment": ref.get("comment")},
        "candidate_count": len(a_cands),
        "hit": hit,
        "best": (dict(best, rel_err=best_rel) if best is not None else None),
        "status": "AGREES" if hit else "TENSION",
    }
    report["validation_status"] = report["alpha_compare"]["status"]

    p = out_dir / "em_lock_compare_v0_1.json"
    p.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md = out_dir / "em_lock_compare_v0_1.md"
    lines = [
        "# EM_LOCK Compare (v0.1)",
        "",
        f"- core: `{report['inputs']['core']}`",
        f"- ref: `{report['inputs']['ref']}`",
        "",
        f"- Validation-status: **{report['validation_status']}**",
        "",
        "## Alpha compare",
        "",
        f"- ref alpha: {ref_val} (tol_rel={tol_rel})",
        f"- candidates: {len(a_cands)}",
    ]
    if hit:
        lines.append(f"- HIT: {hit}")
    else:
        lines.append(f"- BEST: {report['alpha_compare'].get('best')}")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"WROTE: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
