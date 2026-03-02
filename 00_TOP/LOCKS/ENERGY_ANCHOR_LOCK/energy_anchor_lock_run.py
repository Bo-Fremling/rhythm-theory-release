#!/usr/bin/env python3
"""ENERGY_ANCHOR_LOCK (v0.3)

Overlay-only energy/mass scale anchor.

Goal:
  - Use exactly ONE energy anchor in Overlay.
  - Keep Core dimensionless.

Modes (reference key: `scope` in 00_TOP/OVERLAY/energy_anchor_reference.json):

  1) scope = "sector"  (legacy / conservative)
     - Scale ONLY the sector that the anchor belongs to (e/u/d).
     - Uses ratio-ladders (m3=1) derived from FLAVOR_LOCK ratios.
     - Does NOT assume cross-sector absolute comparability.

  2) scope = "global"  (one-anchor global energy scale)
     - Scale ALL available FLAVOR_LOCK sectors (u,d,e) with ONE scale.
     - Uses the raw `masses` arrays emitted by FLAVOR_LOCK.
     - Assumption: FLAVOR_LOCK masses share a common RT-energy normalization.

Neutrinos:
  - Excluded from absolute scaling here (needs separate ν-mechanism lock).

Usage (repo root):
  python3 00_TOP/LOCKS/ENERGY_ANCHOR_LOCK/energy_anchor_lock_run.py

Outputs:
  out/ENERGY_ANCHOR_LOCK/energy_anchor_lock_v0_3.json
  out/ENERGY_ANCHOR_LOCK/energy_anchor_lock_summary_v0_3.md

Exit codes:
  0 = PASS
  2 = FAIL (missing inputs / invalid anchor / freeze mismatch)

Policy:
  - Overlay-only. Unit follows provided anchor.
  - No SI constants used in code; anchor value is user-provided reference.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

VERSION = "v0_3"

# Only use LEPTON_MASS_LOCK override if it is consistent with Overlay lepton ratios.
# This keeps Overlay stable while Core explores PDG-free candidates.
LEPTON_OVERRIDE_MAX_REL_ERR = 1e-3


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


def _ladder_from_ratios(m1_over_m2: float, m2_over_m3: float) -> Tuple[float, float, float]:
    """Return relative masses (m1,m2,m3) up to a common scale, using m3=1."""
    m3 = 1.0
    m2 = m2_over_m3 * m3
    m1 = m1_over_m2 * m2
    return m1, m2, m3


def _parse_anchor_id(anchor_id: str) -> Tuple[bool, str, int, str]:
    try:
        sector, mid = anchor_id.split(":")
        idx = int(mid.replace("m", ""))
        if idx not in (1, 2, 3):
            return False, "anchor_index_invalid", -1, sector
        return True, "ok", idx, sector
    except Exception:
        return False, "anchor_id_parse_fail", -1, ""


def _extract_ratios(obj: Dict[str, Any], key: str) -> Tuple[float, float]:
    sec = obj.get(key, {})
    r = sec.get("ratios", {})
    return float(r.get("m1_over_m2", float("nan"))), float(r.get("m2_over_m3", float("nan")))


def _extract_masses(obj: Dict[str, Any], key: str) -> Tuple[bool, str, Tuple[float, float, float]]:
    sec = obj.get(key, {})
    arr = sec.get("masses", None)
    if not isinstance(arr, list) or len(arr) != 3:
        return False, "masses_missing_or_bad_shape", (float("nan"),) * 3
    try:
        m = tuple(float(x) for x in arr)
    except Exception:
        return False, "masses_non_numeric", (float("nan"),) * 3
    if not all(_finite_pos(x) for x in m):
        return False, "masses_nonpositive_or_nonfinite", m
    return True, "ok", m  # type: ignore


def _max_rel_err_from_lepton_mass_lock(path: Path) -> Tuple[Any, str]:
    """Return (max_rel_err, reason). Prefer overlay_triage if present; else use model.best.errors_rel."""
    try:
        obj = _load_json(path)
        ov = obj.get("overlay_triage")
        if isinstance(ov, dict):
            e = ov.get("errors_rel") or {}
            mx = max(abs(float(e.get("mu_over_e"))), abs(float(e.get("tau_over_mu"))))
            return mx, "ok_overlay_triage"
        best = (((obj.get("model") or {}).get("best") or {}))
        e = best.get("errors_rel") or {}
        mx = max(abs(float(e.get("mu_over_e"))), abs(float(e.get("tau_over_mu"))))
        return mx, "ok_best_errors"
    except Exception as ex:
        return None, f"error:{ex}"


def main() -> int:
    here = Path(__file__).resolve()
    repo = _repo_root_from_here(here)

    ud_path = repo / "out/FLAVOR_LOCK/flavor_ud_v0_9.json"
    enu_path = repo / "out/FLAVOR_LOCK/flavor_enu_v0_9.json"
    ref_path = repo / "00_TOP/OVERLAY/energy_anchor_reference.json"
    freeze_glob = repo / "00_TOP/OVERLAY"

    out_json = repo / f"out/ENERGY_ANCHOR_LOCK/energy_anchor_lock_{VERSION}.json"
    out_md = repo / f"out/ENERGY_ANCHOR_LOCK/energy_anchor_lock_summary_{VERSION}.md"

    missing = [str(p) for p in (ud_path, enu_path, ref_path) if not p.exists()]
    if missing:
        obj = {
            "version": VERSION,
            "gate": {"pass": False, "reason": "missing_inputs", "missing": missing},
        }
        _write_json(out_json, obj)
        _write_text(out_md, "# ENERGY_ANCHOR_LOCK v0.3\n\nFAIL: missing inputs\n")
        return 2

    ud = _load_json(ud_path)
    enu = _load_json(enu_path)
    ref = _load_json(ref_path)

    enabled = bool(ref.get("enabled", False))
    scope = str(ref.get("scope", "sector")).strip().lower()
    anchor_id = str(ref.get("anchor_id", ""))
    anchor_value = ref.get("anchor_value", None)
    unit = str(ref.get("unit", ""))

    checks: Dict[str, Any] = {}

    # Optional freeze enforcement: if a freeze file exists, the reference must match it exactly.
    freeze_files = sorted(freeze_glob.glob("ENERGY_ANCHOR_FREEZE_*.json"))
    if freeze_files:
        freeze_obj = _load_json(freeze_files[0])
        frozen = freeze_obj.get("frozen", {}) if isinstance(freeze_obj, dict) else {}
        freeze_pass = bool((freeze_obj.get("gate", {}) or {}).get("pass", False))
        freeze_match = (
            freeze_pass
            and frozen.get("anchor_id") == anchor_id
            and isinstance(anchor_value, (int, float))
            and float(frozen.get("anchor_value")) == float(anchor_value)
            and frozen.get("unit") == unit
        )
        checks.update({
            "freeze_present": True,
            "freeze_gate_pass": freeze_pass,
            "freeze_match": freeze_match,
            "freeze_file": str(freeze_files[0]),
        })
    else:
        checks.update({
            "freeze_present": False,
            "freeze_gate_pass": True,
            "freeze_match": True,
        })

    checks["anchor_enabled"] = enabled
    checks["anchor_value_is_number"] = isinstance(anchor_value, (int, float))
    checks["anchor_id_present"] = bool(anchor_id)
    checks["unit_present"] = bool(unit)
    checks["scope"] = scope
    checks["scope_valid"] = scope in ("sector", "global")

    ok_id, why_id, idx, anchor_sector = _parse_anchor_id(anchor_id)
    checks["anchor_id_valid"] = ok_id

    # Build ladders from ratios (always computed; useful for reporting)
    u12, u23 = _extract_ratios(ud, "u")
    d12, d23 = _extract_ratios(ud, "d")
    e12, e23 = _extract_ratios(enu, "e")

    checks["ratios_finite_pos"] = all(_finite_pos(x) for x in [u12, u23, d12, d23, e12, e23])

    ladders = {
        "u": _ladder_from_ratios(u12, u23),
        "d": _ladder_from_ratios(d12, d23),
        "e": _ladder_from_ratios(e12, e23),
    }

    masses_relative = {sec: {"m1": m1, "m2": m2, "m3": m3} for sec, (m1, m2, m3) in ladders.items()}

    # Extract raw masses (needed for global mode)
    u_m_ok, u_m_why, u_m = _extract_masses(ud, "u")
    d_m_ok, d_m_why, d_m = _extract_masses(ud, "d")
    e_m_ok, e_m_why, e_m = _extract_masses(enu, "e")

    # Optional override (Overlay only): if LEPTON_MASS_LOCK exists AND matches overlay lepton ratios,
    # use its masses_proxy for e raw masses in global mode.
    lep_path_v5 = repo / "out/LEPTON_MASS_LOCK/lepton_mass_lock_v0_5.json"
    lep_path_v4 = repo / "out/LEPTON_MASS_LOCK/lepton_mass_lock_v0_4.json"
    lep_path_v3 = repo / "out/LEPTON_MASS_LOCK/lepton_mass_lock_v0_3.json"
    lep_path_v2 = repo / "out/LEPTON_MASS_LOCK/lepton_mass_lock_v0_2.json"
    lep_path_v1 = repo / "out/LEPTON_MASS_LOCK/lepton_mass_lock_v0_1.json"

    lep_candidates = [p for p in (lep_path_v5, lep_path_v4, lep_path_v3, lep_path_v2, lep_path_v1) if p.exists()]
    lep_path = None
    lep_best_err = None
    lep_best_reason = None
    for p in lep_candidates:
        mx, why = _max_rel_err_from_lepton_mass_lock(p)
        if mx is None:
            continue
        if (lep_best_err is None) or (float(mx) < float(lep_best_err)):
            lep_best_err = float(mx)
            lep_best_reason = why
            lep_path = p

    lep_override_present = lep_path is not None
    lep_override_used = False
    lep_override_reason = None
    if lep_override_present:
        try:
            assert lep_path is not None
            if lep_best_err is None or lep_best_err > LEPTON_OVERRIDE_MAX_REL_ERR:
                lep_override_reason = f"overlay_mismatch:max_rel_err={lep_best_err} ({lep_best_reason})"
            else:
                lep = _load_json(lep_path)
                best = (((lep.get("model") or {}).get("best") or {}).get("masses_proxy") or None)
                if isinstance(best, list) and len(best) == 3:
                    cand = tuple(float(x) for x in best)
                    if all(_finite_pos(x) for x in cand):
                        e_m = cand
                        e_m_ok = True
                        e_m_why = "ok_overridden_by_lepton_mass_lock"
                        lep_override_used = True
                        lep_override_reason = f"used:{lep_path.name}:max_rel_err={lep_best_err}"
                    else:
                        lep_override_reason = "masses_proxy_nonpositive_or_nonfinite"
                else:
                    lep_override_reason = "masses_proxy_missing_or_bad_shape"
        except Exception as e:
            lep_override_reason = f"error:{e}"

    checks["lepton_mass_lock_override_present"] = lep_override_present
    checks["lepton_mass_lock_override_used"] = lep_override_used
    checks["lepton_mass_lock_override_reason"] = lep_override_reason

    checks["raw_masses_u_ok"] = u_m_ok
    checks["raw_masses_d_ok"] = d_m_ok
    checks["raw_masses_e_ok"] = e_m_ok
    checks["raw_masses_u_reason"] = u_m_why
    checks["raw_masses_d_reason"] = d_m_why
    checks["raw_masses_e_reason"] = e_m_why

    gate_pass = False
    scale = None
    scale_reason = "uncomputed"
    masses_absolute: Dict[str, Dict[str, Any]] = {}

    if not (enabled and isinstance(anchor_value, (int, float)) and anchor_id and unit and ok_id and checks["scope_valid"]):
        scale_reason = "anchor_disabled_or_invalid"
    else:
        if scope == "sector":
            # Conservative: use ratio ladder, scale only anchored sector
            if not checks["ratios_finite_pos"]:
                scale_reason = "ratios_invalid"
            elif anchor_sector not in ladders:
                scale_reason = "anchor_sector_unknown"
            else:
                rel = ladders[anchor_sector][idx - 1]
                if not _finite_pos(rel):
                    scale_reason = "anchor_rel_invalid"
                else:
                    scale = float(anchor_value) / rel
                    if not _finite_pos(scale):
                        scale = None
                        scale_reason = "scale_invalid"
                    else:
                        gate_pass = True
                        m1, m2, m3 = ladders[anchor_sector]
                        masses_absolute[anchor_sector] = {
                            "m1": scale * m1,
                            "m2": scale * m2,
                            "m3": scale * m3,
                            "unit": unit,
                            "scope": "sector",
                        }
                        scale_reason = "ok"

        elif scope == "global":
            # Global: use raw masses arrays, scale all sectors (u,d,e)
            if anchor_sector not in ("u", "d", "e"):
                scale_reason = "anchor_sector_unknown"
            elif not (u_m_ok and d_m_ok and e_m_ok):
                scale_reason = "raw_masses_invalid"
            else:
                raw = {"u": u_m, "d": d_m, "e": e_m}[anchor_sector][idx - 1]
                if not _finite_pos(raw):
                    scale_reason = "anchor_raw_mass_invalid"
                else:
                    scale = float(anchor_value) / raw
                    if not _finite_pos(scale):
                        scale = None
                        scale_reason = "scale_invalid"
                    else:
                        gate_pass = True
                        # scale all three charged sectors
                        labels = {"u": ("u", "c", "t"), "d": ("d", "s", "b"), "e": ("e", "mu", "tau")}
                        for sec, masses in {"u": u_m, "d": d_m, "e": e_m}.items():
                            a, b, c = labels[sec]
                            masses_absolute[sec] = {
                                "m1": scale * masses[0],
                                "m2": scale * masses[1],
                                "m3": scale * masses[2],
                                "labels": [a, b, c],
                                "unit": unit,
                                "scope": "global",
                            }
                        scale_reason = "ok"

    # Enforce freeze match at the end
    gate_pass = bool(gate_pass and checks["freeze_gate_pass"] and checks["freeze_match"])
    if not checks["freeze_gate_pass"]:
        scale_reason = "freeze_gate_fail"
    if not checks["freeze_match"]:
        scale_reason = "freeze_mismatch"

    obj = {
        "version": VERSION,
        "policy": {
            "scope": scope,
            "neutrinos": "excluded",
            "note": "global scope assumes cross-sector common RT normalization for FLAVOR_LOCK masses",
        },
        "inputs": {
            "ud": str(ud_path),
            "enu": str(enu_path),
            "anchor_ref": str(ref_path),
            "lepton_mass_lock": str(lep_path) if lep_path is not None else None,
        },
        "anchor": {
            "enabled": enabled,
            "scope": scope,
            "anchor_id": anchor_id,
            "anchor_value": anchor_value,
            "unit": unit,
            "scale": scale if gate_pass else None,
            "scale_reason": scale_reason,
            "anchor_sector": anchor_sector,
            "anchor_index": idx if ok_id else None,
        },
        "checks": checks,
        "gate": {"pass": gate_pass, "reason": "ok" if gate_pass else scale_reason},
        "masses_absolute": masses_absolute,
        "masses_relative": masses_relative,
        "raw_masses": {
            "u": list(u_m) if u_m_ok else None,
            "d": list(d_m) if d_m_ok else None,
            "e": list(e_m) if e_m_ok else None,
        },
        "notes": [
            "Overlay-only: unit follows anchor; no constants used.",
            "Exactly one anchor; Core remains dimensionless.",
            "Neutrinos excluded (needs separate ν-mechanism lock).",
            "If LEPTON_MASS_LOCK override is present+used, e raw masses are replaced by its masses_proxy (scaffold).",
        ],
    }

    _write_json(out_json, obj)

    # Markdown summary
    lines = []
    lines.append("# ENERGY_ANCHOR_LOCK v0.3")
    lines.append("")
    lines.append(f"Overall: {'PASS' if gate_pass else 'FAIL'}")
    lines.append("")
    lines.append("## Anchor")
    lines.append("")
    lines.append(f"- enabled: {enabled}")
    lines.append(f"- scope: {scope}")
    lines.append(f"- anchor_id: {anchor_id}")
    lines.append(f"- anchor_value: {anchor_value}")
    lines.append(f"- unit: {unit}")
    lines.append(f"- scale_reason: {scale_reason}")
    if gate_pass:
        lines.append(f"- scale: {scale}")
    lines.append("")
    lines.append("## Checks")
    lines.append("")
    for k, v in checks.items():
        if isinstance(v, bool):
            lines.append(f"- {k}: {'PASS' if v else 'FAIL'}")
        else:
            lines.append(f"- {k}: {v}")
    lines.append("")

    if gate_pass:
        lines.append("## Absolute masses")
        lines.append("")
        if scope == "sector":
            sec = anchor_sector
            labels = {"e": ("e", "mu", "tau"), "u": ("u", "c", "t"), "d": ("d", "s", "b")}
            if sec in masses_absolute:
                m = masses_absolute[sec]
                a, b, c = labels.get(sec, ("m1", "m2", "m3"))
                lines.append(f"- {sec} ({a},{b},{c}): m1={m.get('m1')}, m2={m.get('m2')}, m3={m.get('m3')} {m.get('unit')}")
        else:
            for sec in ("e", "u", "d"):
                if sec in masses_absolute:
                    m = masses_absolute[sec]
                    lab = m.get("labels", ["m1", "m2", "m3"])
                    lines.append(f"- {sec} ({','.join(lab)}): m1={m.get('m1')}, m2={m.get('m2')}, m3={m.get('m3')} {m.get('unit')}")
        lines.append("")

    lines.append("## Relative ladders (dimensionless; m3=1)")
    lines.append("")
    for sec, m in masses_relative.items():
        lines.append(f"- {sec}: m1={m['m1']}, m2={m['m2']}, m3={m['m3']}")
    lines.append("")

    _write_text(out_md, "\n".join(lines) + "\n")

    return 0 if gate_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
