#!/usr/bin/env python3
"""SM29 data-match triage (Overlay-only).

Creates:
  out/SM_PARAM_INDEX/sm29_data_match_v0_1.json
  out/SM_PARAM_INDEX/sm29_data_match_summary_v0_1.md

This is NOT a Core derivation. It compares already-produced artifacts against
reference rules (some are external PDG/CODATA; some are explicit overlay
freeze/identity checks). The goal is only ✅/❌/🟡 marking in SM_29_REPORT.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class MatchResult:
    key: str
    status: str  # PASS/FAIL/TODO
    icon: str
    value: Optional[float]
    ref: Optional[float]
    unit: str
    delta: Optional[float]
    delta_rel: Optional[float]
    note: str


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _safe_get(d: Dict[str, Any], path: Tuple[str, ...]) -> Any:
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _match_numeric(key: str, value: Optional[float], spec: Dict[str, Any]) -> MatchResult:
    unit = spec.get("unit", "")

    def fmt(x: float) -> str:
        return f"{x:.6g}"

    if value is None:
        return MatchResult(key, "TODO", "🟡", None, spec.get("value"), unit, None, None, "saknar värde/artefakt")

    # Range-based check
    if "range" in spec:
        lo, hi = spec["range"]
        ok = lo <= value <= hi
        return MatchResult(
            key,
            "PASS" if ok else "FAIL",
            "✅" if ok else "❌",
            value,
            spec.get("value"),
            unit,
            None,
            None,
            f"RT={fmt(value)} {unit}; range {lo:g}–{hi:g} {unit}",
        )

    ref = spec.get("value")
    if ref is None:
        return MatchResult(key, "TODO", "🟡", value, None, unit, None, None, "ref saknas")

    delta = value - float(ref)
    delta_rel = None if ref == 0 else (delta / float(ref))

    ok = True
    if "tol_abs" in spec:
        ok = ok and (abs(delta) <= float(spec["tol_abs"]))
    if "tol_rel" in spec and delta_rel is not None:
        ok = ok and (abs(delta_rel) <= float(spec["tol_rel"]))

    note_bits = []
    if "tol_abs" in spec:
        note_bits.append(f"|Δ|≤{float(spec['tol_abs']):g} {unit}")
    if "tol_rel" in spec:
        note_bits.append(f"|Δ|/ref≤{float(spec['tol_rel']):g}")
    tol_note = ", ".join(note_bits) if note_bits else ""
    note = f"RT={fmt(value)} {unit}; ref={fmt(float(ref))} {unit}; Δ={fmt(delta)} {unit}"
    if tol_note:
        note = f"{note}; {tol_note}"

    return MatchResult(
        key,
        "PASS" if ok else "FAIL",
        "✅" if ok else "❌",
        value,
        float(ref),
        unit,
        float(delta),
        None if delta_rel is None else float(delta_rel),
        note,
    )


def _match_nu_dm2_gate(
    *,
    dm21: Optional[float],
    dm31: Optional[float],
    spec_dm21: Dict[str, Any],
    spec_dm31: Dict[str, Any],
    spec_gate: Dict[str, Any],
) -> MatchResult:
    """Compound triage: PASS iff both Δm² values are inside their ranges (Overlay-only)."""

    unit = spec_gate.get("unit", "bool")

    if dm21 is None or dm31 is None:
        return MatchResult("nu_dm2_gate", "TODO", "🟡", None, spec_gate.get("value"), unit, None, None, "saknar nu_mechanism Δm²")

    r21 = spec_dm21.get("range")
    r31 = spec_dm31.get("range")
    if not (isinstance(r21, list) and len(r21) == 2 and isinstance(r31, list) and len(r31) == 2):
        return MatchResult("nu_dm2_gate", "TODO", "🟡", None, spec_gate.get("value"), unit, None, None, "ref range saknas för ν Δm²")

    lo21, hi21 = float(r21[0]), float(r21[1])
    lo31, hi31 = float(r31[0]), float(r31[1])

    ok21 = lo21 <= float(dm21) <= hi21
    ok31 = lo31 <= float(dm31) <= hi31
    ok = ok21 and ok31

    val = 1.0 if ok else 0.0
    icon = "✅" if ok else "❌"
    status = "PASS" if ok else "FAIL"

    note = (
        f"dm21={dm21:.6g} eV^2 (range {lo21:g}–{hi21:g}); "
        f"dm31={dm31:.6g} eV^2 (range {lo31:g}–{hi31:g})"
    )

    return MatchResult("nu_dm2_gate", status, icon, val, float(spec_gate.get("value", 1.0)), unit, None, None, note)


def _load_latest_compare_index(repo_root: Path) -> Optional[Path]:
    """Pick the newest out/COMPARE_SM29_INDEX/sm29_compare_index_*.json if present."""
    d = repo_root / "out" / "COMPARE_SM29_INDEX"
    if not d.exists():
        return None
    cands = sorted(d.glob("sm29_compare_index_*.json"), key=lambda p: p.stat().st_mtime)
    return cands[-1] if cands else None


def _extract_from_compare_index(repo_root: Path) -> Dict[str, Dict[str, Any]]:
    """Return map ref_key -> detail payload from the latest compare index.

    This is Overlay-only triage: it reuses the same numbers/tolerances already
    embedded in the compare index (no second source of truth).
    """
    idxp = _load_latest_compare_index(repo_root)
    if not idxp or not idxp.exists():
        return {}
    try:
        obj = _read_json(idxp)
    except Exception:
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    for e in (obj.get("entries") or []):
        for d in (e.get("details") or []):
            k = d.get("ref")
            if not isinstance(k, str) or not k:
                continue
            core = d.get("core")
            val = None
            if isinstance(core, (int, float)):
                val = float(core)
            elif isinstance(core, list) and core and isinstance(core[0], (int, float)):
                val = float(core[0])
            elif isinstance(core, dict):
                for kk in ("preferred", "hit"):
                    vv = core.get(kk)
                    if isinstance(vv, (int, float)):
                        val = float(vv)
                        break
                if val is None:
                    cands = core.get("candidates")
                    if isinstance(cands, list) and cands and isinstance(cands[0], (int, float)):
                        val = float(cands[0])
            refv = d.get("ref_value")
            refv = float(refv) if isinstance(refv, (int, float)) else None
            ok = d.get("ok")
            okb = bool(ok) if isinstance(ok, bool) else None

            unit = d.get("unit") if isinstance(d.get("unit"), str) else ""
            tol = d.get("tol") if isinstance(d.get("tol"), str) else ""
            note = d.get("note") if isinstance(d.get("note"), str) else ""

            out[k] = {
                "ok": okb,
                "value": val,
                "ref": refv,
                "unit": unit,
                "tol": tol,
                "note": note,
                "source_compare_index": str(idxp.relative_to(repo_root)).replace('\\','/'),
            }
    return out


def build_data_match(repo_root: Path) -> Dict[str, Any]:
    # Prefer v0_2 if present (legacy v0_1 kept for backward compatibility)
    ref_p2 = repo_root / "00_TOP/OVERLAY/sm29_data_reference_v0_2.json"
    ref_p1 = repo_root / "00_TOP/OVERLAY/sm29_data_reference_v0_1.json"
    ref_p = ref_p2 if ref_p2.exists() else ref_p1

    # Primary data source: latest compare index (already contains ref_value + tol + ok)
    idxp = _load_latest_compare_index(repo_root)
    cmp = _extract_from_compare_index(repo_root)

    results: Dict[str, MatchResult] = {}

    # 1) All compare-index keys
    for k, v in sorted(cmp.items()):
        ok = v.get("ok")
        if ok is True:
            status, icon = "PASS", "✅"
        elif ok is False:
            status, icon = "FAIL", "❌"
        else:
            status, icon = "TODO", "🟡"

        val = v.get("value")
        refv = v.get("ref")
        unit = v.get("unit") or ""

        delta = None
        delta_rel = None
        if isinstance(val, (int, float)) and isinstance(refv, (int, float)):
            delta = float(val) - float(refv)
            if float(refv) != 0.0:
                delta_rel = delta / float(refv)

        note_bits = []
        if v.get("tol"):
            note_bits.append(v.get("tol"))
        if v.get("note"):
            note_bits.append(v.get("note"))
        note = "; ".join([str(x) for x in note_bits if x])

        results[k] = MatchResult(k, status, icon, None if val is None else float(val), None if refv is None else float(refv), unit, delta, delta_rel, note)

    # 2) κ freeze check (Overlay-only, independent of compare-index)
    try:
        ref = _read_json(ref_p)
        spec = (ref.get("refs") or {}).get("kappa_L_m_per_RT") or {}
        kappa_p = repo_root / "00_TOP/OVERLAY/kappa_global.json"
        if kappa_p.exists():
            kg = _read_json(kappa_p)
            kval = kg.get("kappa_L_m_per_RT")
            kval = float(kval) if isinstance(kval, (int, float)) else None
        else:
            kval = None
        results["kappa_L_m_per_RT"] = _match_numeric("kappa_L_m_per_RT", kval, spec)
    except Exception:
        # leave κ absent rather than crashing
        pass

    payload = {
        "meta": {
            "version": "v0.4",
            "generated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "reference_file": str(ref_p.relative_to(repo_root)).replace('\\','/'),
            "compare_index": (str(idxp.relative_to(repo_root)).replace("\\","/") if idxp else None),
        },
        "results": {
            k: {
                "status": r.status,
                "icon": r.icon,
                "value": r.value,
                "ref": r.ref,
                "unit": r.unit,
                "delta": r.delta,
                "delta_rel": r.delta_rel,
                "note": r.note,
            }
            for k, r in results.items()
        },
    }
    return payload


def write_artifacts(repo_root: Path) -> Tuple[Path, Path]:
    out_dir = repo_root / "out/SM_PARAM_INDEX"
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = build_data_match(repo_root)
    jpath = out_dir / "sm29_data_match_v0_1.json"
    jpath.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    # summary md
    res = payload["results"]
    counts = {"✅": 0, "❌": 0, "🟡": 0}
    for v in res.values():
        counts[v["icon"]] = counts.get(v["icon"] , 0) + 1

    lines = []
    lines.append("# SM29 data-match summary (v0.4)\n\n")
    lines.append(f"Generated: {payload['meta']['generated']}\n\n")
    lines.append(f"Reference: `{payload['meta']['reference_file']}`\n\n")
    lines.append(f"Counts: ✅ {counts['✅']} | ❌ {counts['❌']} | 🟡 {counts['🟡']}\n\n")
    lines.append("| Key | Result | Value | Ref | Note |\n")
    lines.append("|---|---:|---:|---:|---|\n")
    for k in sorted(res.keys()):
        v = res[k]
        val = "—" if v["value"] is None else f"{v['value']:.12g}"
        refv = "—" if v["ref"] is None else f"{v['ref']:.12g}"
        unit = v.get("unit") or ""
        lines.append(f"| `{k}` | {v['icon']} {v['status']} | {val} {unit} | {refv} {unit} | {v['note']} |\n")

    mpath = out_dir / "sm29_data_match_summary_v0_1.md"
    mpath.write_text("".join(lines), encoding="utf-8")
    return jpath, mpath


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    write_artifacts(repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())