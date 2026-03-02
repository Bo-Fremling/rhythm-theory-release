#!/usr/bin/env python3
"""Verify NU_MECHANISM_LOCK outputs.

Two layers:
  1) Core-policy gates (no external refs)
  2) Overlay triage (optional): map dimensionless scaffold to eV using an
     explicit anchor (ENERGY_ANCHOR_LOCK preferred; else sm29_data_reference).

Overlay triage is informational only and MUST NOT be used as a Core gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple

REPO = Path(__file__).resolve().parents[3]


def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _pick_latest_nu_json() -> Optional[Path]:
    out = REPO / "out/NU_MECHANISM_LOCK"
    cand = [
        out / "nu_mechanism_lock_v0_3.json",
        out / "nu_mechanism_lock_v0_2.json",
        out / "nu_mechanism_lock_v0_1.json",
    ]
    for p in cand:
        if p.exists():
            return p
    return None


def _extract_me_anchor_eV() -> Tuple[Optional[float], str]:
    """Return (m_e in eV, src). Overlay-only."""

    # Prefer ENERGY_ANCHOR_LOCK if present and PASS.
    ea = REPO / "out/ENERGY_ANCHOR_LOCK/energy_anchor_lock_v0_3.json"
    if ea.exists():
        try:
            obj = load_json(ea)
            if bool((obj.get("gate") or {}).get("pass")):
                e = (obj.get("masses_absolute") or {}).get("e") or {}
                val = e.get("m1")
                unit = (e.get("unit") or obj.get("anchor", {}).get("unit") or "").strip().lower()
                if isinstance(val, (int, float)):
                    if unit == "mev":
                        return float(val) * 1e6, "ENERGY_ANCHOR_LOCK:v0_3 (MeV→eV)"
                    if unit == "gev":
                        return float(val) * 1e9, "ENERGY_ANCHOR_LOCK:v0_3 (GeV→eV)"
                    if unit == "ev":
                        return float(val), "ENERGY_ANCHOR_LOCK:v0_3 (eV)"
        except Exception:
            pass

    # Fallback: explicit refs file.
    refp = REPO / "00_TOP/OVERLAY/sm29_data_reference_v0_1.json"
    if refp.exists():
        try:
            ref = load_json(refp)
            me = (((ref.get("refs") or {}).get("m_e") or {}).get("value"))
            unit = (((ref.get("refs") or {}).get("m_e") or {}).get("unit"))
            if isinstance(me, (int, float)):
                u = (unit or "").strip().lower()
                if u == "mev":
                    return float(me) * 1e6, "sm29_data_reference_v0_1 (MeV→eV)"
                if u == "gev":
                    return float(me) * 1e9, "sm29_data_reference_v0_1 (GeV→eV)"
                if u == "ev":
                    return float(me), "sm29_data_reference_v0_1 (eV)"
        except Exception:
            pass

    return None, "missing_anchor"


def _overlay_triage(nu: dict) -> Optional[dict]:
    """Compute an eV mapping for Pattern A (or first pattern), if possible."""
    me_eV, src = _extract_me_anchor_eV()
    if me_eV is None:
        return {
            "available": False,
            "reason": "missing_anchor",
            "anchor_source": src,
        }

    pats = (((nu.get("results") or {}).get("patterns")) or [])
    if not pats:
        return {
            "available": False,
            "reason": "missing_patterns",
            "anchor_source": src,
            "m_e_eV": me_eV,
        }

    pat = None
    for it in pats:
        if isinstance(it, dict) and it.get("id") == "A":
            pat = it
            break
    pat = pat or (pats[0] if isinstance(pats[0], dict) else None)
    if not isinstance(pat, dict):
        return {
            "available": False,
            "reason": "bad_pattern_shape",
            "anchor_source": src,
            "m_e_eV": me_eV,
        }

    m0_over_me = pat.get("m0_over_m_e")
    m_over_me = pat.get("m_over_m_e")
    if not isinstance(m0_over_me, (int, float)) or not (isinstance(m_over_me, list) and len(m_over_me) == 3):
        return {
            "available": False,
            "reason": "pattern_missing_dimless",
            "anchor_source": src,
            "m_e_eV": me_eV,
        }

    m0 = float(me_eV) * float(m0_over_me)
    m = [float(me_eV) * float(x) for x in m_over_me]
    dm21 = (m[1] ** 2) - (m[0] ** 2)
    dm31 = (m[2] ** 2) - (m[0] ** 2)
    ratio = (dm31 / dm21) if dm21 != 0 else None

    return {
        "available": True,
        "anchor_source": src,
        "m_e_eV": me_eV,
        "pattern_id": pat.get("id"),
        "n": pat.get("n"),
        "m0_eV": m0,
        "m_eV": m,
        "delta_m2_eV2": {"dm21": dm21, "dm31": dm31, "dm31_over_dm21": ratio},
    }


def main() -> int:
    p = _pick_latest_nu_json()
    if p is None or not p.exists():
        print("MISSING: out/NU_MECHANISM_LOCK/nu_mechanism_lock_v0_3.json (or older)")
        return 2

    obj = load_json(p)
    gates = obj.get("gates") or {}
    ok = bool(obj.get("gate", {}).get("pass", False))

    out = {
        "version": obj.get("version"),
        "inputs": {"json": str(p.relative_to(REPO))},
        "gates": gates,
        "overall": "PASS" if ok else "FAIL",
    }

    out_dir = REPO / "out/NU_MECHANISM_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "nu_mechanism_lock_verify_latest.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        f"# NU_MECHANISM_LOCK verify ({obj.get('version')})",
        "",
        "Core gates:",
    ]
    for k, v in gates.items():
        lines.append(f"- {k}: {'PASS' if v else 'FAIL'}")
    lines += [
        "",
        f"Overall (policy only): {'PASS' if ok else 'FAIL'}",
    ]

    (out_dir / "nu_mechanism_lock_verify_latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Optional overlay triage (informational)
    tri = _overlay_triage(obj)
    if tri is not None:
        (out_dir / "nu_mechanism_lock_overlay_triage_latest.json").write_text(json.dumps(tri, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tlines = [
            "# NU_MECHANISM_LOCK overlay triage (informational)",
            "",
            f"Available: {bool(tri.get('available'))}",
            f"Anchor: {tri.get('anchor_source')}",
        ]
        if tri.get("available"):
            dm = tri.get("delta_m2_eV2") or {}
            tlines += [
                "",
                f"Pattern: {tri.get('pattern_id')} n={tri.get('n')}",
                f"m0: {tri.get('m0_eV')} eV",
                f"Δm²21: {dm.get('dm21')} eV²",
                f"Δm²31: {dm.get('dm31')} eV²",
                f"ratio (31/21): {dm.get('dm31_over_dm21')}",
            ]
        else:
            tlines += ["", f"Reason: {tri.get('reason')}"]
        (out_dir / "nu_mechanism_lock_overlay_triage_latest.md").write_text("\n".join(tlines) + "\n", encoding="utf-8")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
