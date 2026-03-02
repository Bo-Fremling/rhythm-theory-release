#!/usr/bin/env python3
"""TOP_PROXY_LOCK compare (Overlay-only).

Compares Core proxy ratios derived from FLAVOR_LOCK UD masses against
overlay-only reference ranges.

IMPORTANT
- Overlay-only: may read 00_TOP/OVERLAY/*
- MUST NOT be called from any *_coregen.py or influence Core selection.
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


def _pick_latest(dirpath: Path, pattern: str) -> Optional[Path]:
    c = sorted(dirpath.glob(pattern))
    return c[-1] if c else None


def _pick_overlay_ref() -> Optional[Path]:
    overlay = REPO / "00_TOP" / "OVERLAY"
    c = sorted(overlay.glob("sm29_data_reference*.json"))
    return c[-1] if c else None


def _as_float(x):
    try:
        return float(x)
    except Exception:
        return None


def _tol_ok(val: float, ref: dict) -> tuple[bool, str]:
    if "range" in ref and isinstance(ref["range"], list) and len(ref["range"]) == 2:
        lo, hi = [float(z) for z in ref["range"]]
        return (lo <= val <= hi), f"range[{lo},{hi}]"
    if "tol_abs" in ref:
        tol = float(ref["tol_abs"])
        rv = float(ref.get("value"))
        return abs(val - rv) <= tol, f"tol_abs={tol}"
    if "tol_rel" in ref:
        tol = float(ref["tol_rel"])
        rv = float(ref.get("value"))
        return abs(val - rv) <= tol * abs(rv), f"tol_rel={tol}"
    if "value" in ref:
        return val == float(ref["value"]), "exact"
    return False, "no_ref"


def main() -> int:
    core_dir = REPO / "out" / f"CORE_{LOCK}"
    core_path = _pick_latest(core_dir, "top_proxy_core_v*.json")
    if not core_path:
        raise SystemExit(f"Missing core artifact in {core_dir}")

    ref_path = _pick_overlay_ref()
    refs = (_read_json(ref_path).get("refs") or {}) if ref_path else {}

    core = _read_json(core_path)
    vals = core.get("values") if isinstance(core, dict) else None

    tests = []

    def add_test(label: str, core_val, ref_key: str):
        r = refs.get(ref_key)
        v = _as_float(core_val)
        if r is None or v is None:
            return
        ok, tol = _tol_ok(v, r)
        tests.append({
            "ref": ref_key,
            "label": label,
            "core": v,
            "ref_value": r.get("value") if "value" in r else r.get("range"),
            "ok": ok,
            "tol": tol,
            "unit": r.get("unit"),
        })

    if isinstance(vals, dict):
        add_test("mt/mb proxy", (vals.get("mt_over_mb_proxy")), "m_t_over_m_b")

        u_rat = vals.get("u_ratios") if isinstance(vals.get("u_ratios"), dict) else {}
        d_rat = vals.get("d_ratios") if isinstance(vals.get("d_ratios"), dict) else {}

        add_test("mu/mc proxy", u_rat.get("m1_over_m2"), "m_u_over_m_c")
        add_test("mc/mt proxy", u_rat.get("m2_over_m3"), "m_c_over_m_t")
        add_test("md/ms proxy", d_rat.get("m1_over_m2"), "m_d_over_m_s")
        add_test("ms/mb proxy", d_rat.get("m2_over_m3"), "m_s_over_m_b")

    status = "UNTESTED"
    if tests:
        status = "AGREES" if all(t["ok"] for t in tests) else "TENSION"

    out = {
        "version": "v0.2",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "lock": LOCK,
        "policy": {"overlay_only": True, "feeds_back": False},
        "core_artifact": str(core_path.relative_to(REPO)).replace("\\", "/"),
        "overlay_ref": str(ref_path.relative_to(REPO)).replace("\\", "/") if ref_path else None,
        "validation_status": status,
        "tests": tests,
        "note": "Proxy ratios only; SI mapping is overlay-only and must not feed back into Core.",
    }

    out_dir = REPO / "out" / f"COMPARE_{LOCK}"
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / "top_proxy_compare_v0_2.json"
    jp.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    mp = out_dir / "top_proxy_compare_v0_2.md"
    lines = [
        "# TOP_PROXY_LOCK compare (v0.2)",
        "",
        f"- core: `{out['core_artifact']}`",
        f"- overlay_ref: `{out['overlay_ref']}`",
        f"- status: **{status}**",
        "",
        "| Test | Core | Ref | OK |", "|---|---:|---:|:---:|",
    ]
    for tt in tests:
        lines.append(f"| {tt['label']} ({tt['ref']}) | {tt['core']} | {tt['ref_value']} | {'✓' if tt['ok'] else '✗'} |")
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"WROTE: {jp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
