#!/usr/bin/env python3
"""PPN_LOCK compare (Overlay-only; NO FEEDBACK).

Reads
  - out/CORE_PPN_LOCK/ppn_lock_core_v0_1.json
  - 00_TOP/OVERLAY/sm29_data_reference_*.json (ppn_gamma, ppn_beta)

Writes
  - out/COMPARE_PPN_LOCK/ppn_lock_compare_v0_1.json
  - out/COMPARE_PPN_LOCK/ppn_lock_compare_v0_1.md
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


REPO = Path(__file__).resolve().parents[3]


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _pick_overlay_ref() -> Optional[Path]:
    overlay = REPO / "00_TOP" / "OVERLAY"
    cands = sorted(overlay.glob("sm29_data_reference*.json"))
    return cands[-1] if cands else None


def _ok(val: float, ref: dict) -> bool:
    if "tol_abs" in ref:
        return abs(val - float(ref["value"])) <= float(ref["tol_abs"])
    if "tol_rel" in ref:
        rv = float(ref["value"])
        return abs(val - rv) <= float(ref["tol_rel"]) * abs(rv)
    return val == float(ref.get("value"))


def main() -> int:
    core_p = REPO / "out" / "CORE_PPN_LOCK" / "ppn_lock_core_v0_1.json"
    if not core_p.exists():
        print("MISSING core PPN artifact; run ppn_lock_coregen.py first")
        return 2

    ref_p = _pick_overlay_ref()
    if not ref_p:
        print("MISSING overlay ref; cannot compare")
        return 3

    core = _load_json(core_p)
    refs = (_load_json(ref_p).get("refs") or {})

    gamma_ref = refs.get("ppn_gamma")
    beta_ref = refs.get("ppn_beta")

    gamma = float(core.get("ppn_gamma"))
    beta = float(core.get("ppn_beta"))

    det = []
    if gamma_ref:
        det.append({"ref": "ppn_gamma", "core": gamma, "ref_value": gamma_ref.get("value"), "ok": _ok(gamma, gamma_ref), "tol": gamma_ref.get("tol_abs") or gamma_ref.get("tol_rel")})
    if beta_ref:
        det.append({"ref": "ppn_beta", "core": beta, "ref_value": beta_ref.get("value"), "ok": _ok(beta, beta_ref), "tol": beta_ref.get("tol_abs") or beta_ref.get("tol_rel")})

    status = "AGREES" if det and all(d["ok"] for d in det) else ("TENSION" if det else "UNTESTED")

    report = {
        "version": "ppn_compare_v0_1",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "policy": {"overlay_only": True, "feeds_back": False},
        "inputs": {
            "core": str(core_p.relative_to(REPO)).replace("\\", "/"),
            "overlay_ref": str(ref_p.relative_to(REPO)).replace("\\", "/"),
        },
        "validation_status": status,
        "details": det,
    }

    out_dir = REPO / "out" / "COMPARE_PPN_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "ppn_lock_compare_v0_1.json"
    out_md = out_dir / "ppn_lock_compare_v0_1.md"
    out_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# PPN_LOCK Compare (v0.1)",
        "",
        f"- status: **{status}**",
        "",
        "| Key | Core | Ref | OK |",
        "|---|---:|---:|---|",
    ]
    for d in det:
        lines.append(f"| {d['ref']} | {d['core']} | {d['ref_value']} | {'OK' if d['ok'] else 'FAIL'} |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"WROTE: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
