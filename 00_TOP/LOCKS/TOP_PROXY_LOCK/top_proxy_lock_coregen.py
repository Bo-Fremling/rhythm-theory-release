#!/usr/bin/env python3
"""TOP_PROXY_LOCK coregen (NO-FACIT).

Goal
- Expose a *Core-only* proxy for the heavy up/down hierarchy, mainly mt/mb,
  derived from already Core-generated FLAVOR_LOCK UD masses.

Important
- This lock does NOT claim SI masses.
- This lock MUST NOT read overlay or any *reference*.json.
- It only computes ratios from existing Core artifacts.

Input
- out/CORE_FLAVOR_LOCK/flavor_ud_core_v0_9.json (or newest available)

Output
- out/CORE_TOP_PROXY_LOCK/top_proxy_core_v0_2.json
- out/CORE_TOP_PROXY_LOCK/top_proxy_core_v0_2.md

Derivation-status
- DERIVED (because it's a deterministic function of a Core artifact).

Validation-status
- UNTESTED (Core stage).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[3]
LOCK = Path(__file__).resolve().parent.name


def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _pick_flavor_ud() -> Path:
    base = REPO / "out" / "CORE_FLAVOR_LOCK"
    # Prefer newest known file name(s)
    for name in [
        "flavor_ud_core_v0_9.json",
        "flavor_ud_core_v0_8.json",
        "flavor_ud_core_v0_7.json",
    ]:
        p = base / name
        if p.exists():
            return p
    # Fallback: pick any flavor_ud_core_*.json deterministically
    cands = sorted(base.glob("flavor_ud_core_*.json"))
    if cands:
        return cands[-1]
    raise FileNotFoundError("Missing out/CORE_FLAVOR_LOCK/flavor_ud_core_*.json")


def main() -> int:
    out_dir = REPO / "out" / f"CORE_{LOCK}"
    out_dir.mkdir(parents=True, exist_ok=True)

    ud_path = _pick_flavor_ud()
    ud = _read_json(ud_path)

    u = ud.get("u") if isinstance(ud, dict) else None
    d = ud.get("d") if isinstance(ud, dict) else None

    def _m3(block: dict) -> Optional[float]:
        if not isinstance(block, dict):
            return None
        masses = block.get("masses")
        if isinstance(masses, list) and len(masses) == 3:
            try:
                return float(masses[2])
            except Exception:
                return None
        return None

    mt = _m3(u)
    mb = _m3(d)

    mt_over_mb = (mt / mb) if (mt is not None and mb is not None and mb != 0) else None
    def _ratios(block: dict) -> Optional[dict]:
        if not isinstance(block, dict):
            return None
        masses = block.get("masses")
        if not (isinstance(masses, list) and len(masses) == 3):
            return None
        try:
            m1, m2, m3 = [float(x) for x in masses]
        except Exception:
            return None
        if m2 == 0 or m3 == 0:
            return None
        return {"m1_over_m2": m1 / m2, "m2_over_m3": m2 / m3}

    u_rat = _ratios(u) if isinstance(u, dict) else None
    d_rat = _ratios(d) if isinstance(d, dict) else None

    out = {
        "version": "v0.2",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "lock": LOCK,
        "derivation_status": "DERIVED",
        "validation_status": "UNTESTED",
        "inputs": {
            "flavor_ud": str(ud_path.relative_to(REPO)).replace("\\", "/"),
        },
        "core_definition": {
            "u_family_masses": "Dimensionless proxy masses from FLAVOR_LOCK (u,c,t) in Core-normalized units.",
            "d_family_masses": "Dimensionless proxy masses from FLAVOR_LOCK (d,s,b) in Core-normalized units.",
            "u_family_ratios": "Ratios within u-family: m1/m2 and m2/m3 (dimensionless proxy).",
            "d_family_ratios": "Ratios within d-family: m1/m2 and m2/m3 (dimensionless proxy).",
            "mt_over_mb_proxy": "mt_over_mb := u_m3 / d_m3 (dimensionless proxy).",
        },
        "values": {
            "u_masses": (u.get("masses") if isinstance(u, dict) else None),
            "d_masses": (d.get("masses") if isinstance(d, dict) else None),
            "mt_proxy": mt,
            "mb_proxy": mb,
            "u_ratios": u_rat,
            "d_ratios": d_rat,
            "mt_over_mb_proxy": mt_over_mb,
            "unit": "dimensionless (Core proxy)",
        },
        "notes": [
            "This is a Core-only proxy ratio derived from FLAVOR_LOCK UD masses.",
            "It is NOT an SI mass ratio; any SI mapping is overlay-only and must not feed back into Core.",
        ],
    }

    jp = out_dir / "top_proxy_core_v0_2.json"
    jp.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    mp = out_dir / "top_proxy_core_v0_2.md"
    lines = [
        "# TOP_PROXY_LOCK Core (v0.2)",
        "",
        "- Derivation-status: **DERIVED**",
        "- Validation-status: **UNTESTED**",
        "",
        f"Input: `{out['inputs']['flavor_ud']}`",
        "",
        "## Values (Core proxy)",
        f"- mt_proxy = {mt}",
        f"- mb_proxy = {mb}",
        f"- mt/mb (proxy) = {mt_over_mb}",
        "",
        "(No SI mapping; no facit.)",
    ]
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Back-compat: keep v0.1 path for older consumers
    legacy = out_dir / "top_proxy_core_v0_1.json"
    if not legacy.exists():
        legacy.write_text(
            json.dumps({"version": "v0.1", "deprecated": True, "migrated_to": "v0.2"}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print(f"WROTE: {jp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
