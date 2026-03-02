#!/usr/bin/env python3
"""SM29 index compare (Overlay-only; NO FEEDBACK).

Reads
  - out/CORE_SM29_INDEX/sm29_core_index_*.json
  - 00_TOP/OVERLAY/sm29_data_reference_*.json

Writes
  - out/COMPARE_SM29_INDEX/sm29_compare_index_v0_9.json
  - out/COMPARE_SM29_INDEX/sm29_compare_index_v0_9.md

Notes
  - This script may read overlay reference numbers.
  - It MUST NOT influence any Core candidate selection.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


REPO = Path(__file__).resolve().parents[3]


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _pick_latest(pattern: str) -> Optional[Path]:
    def _vk(p: Path) -> tuple[int, int]:
        m = re.search(r"_v(\d+)(?:_(\d+))?$", p.stem)
        if m:
            return (int(m.group(1)), int(m.group(2) or 0))
        return (0, 0)

    cands = list((REPO / "out" / "CORE_SM29_INDEX").glob(pattern))
    return max(cands, key=_vk) if cands else None


def _pick_overlay_ref() -> Optional[Path]:
    overlay = REPO / "00_TOP" / "OVERLAY"
    cands = sorted(overlay.glob("sm29_data_reference*.json"))
    return cands[-1] if cands else None


def _as_float(x):
    try:
        return float(x)
    except Exception:
        return None


def _tol_ok(core_val: float, ref: dict) -> tuple[bool, str]:
    # boolean gate
    if str(ref.get("unit")) == "bool":
        ok = (float(core_val) == float(ref.get("value")))
        return ok, "bool"

    if "range" in ref and isinstance(ref["range"], list) and len(ref["range"]) == 2:
        lo, hi = ref["range"]
        ok = (core_val >= float(lo)) and (core_val <= float(hi))
        return ok, f"range[{lo},{hi}]"
    if "tol_abs" in ref:
        tol = float(ref["tol_abs"])
        ok = abs(core_val - float(ref["value"])) <= tol
        return ok, f"tol_abs={tol}"
    if "tol_rel" in ref:
        tol = float(ref["tol_rel"])
        rv = float(ref["value"])
        ok = abs(core_val - rv) <= tol * abs(rv)
        return ok, f"tol_rel={tol}"

    ok = core_val == float(ref.get("value"))
    return ok, "exact"


def _classify_status(core_derivation: str, details: list[dict]) -> str:
    """Validation-status policy.

    - AGREES: all required comparisons have any-hit OK.
    - TENSION: mismatch *and* Core claims DERIVED.
    - COMPARED: mismatch but Core is still CANDIDATE-SET/HYP/BLANK.
    - UNTESTED: no details.
    """
    if not details:
        return "UNTESTED"
    if all(bool(d.get("ok")) for d in details):
        return "AGREES"
    if str(core_derivation).upper() == "DERIVED":
        return "TENSION"
    return "COMPARED"




def _lepton_ref_ratios(refs: dict) -> Optional[dict]:
    """Compute reference lepton mass ratios from overlay refs.

    Uses m_e, m_mu, m_tau. Ratio tol_rel is conservatively summed.
    """
    try:
        me = refs.get("m_e") or {}
        mm = refs.get("m_mu") or {}
        mt = refs.get("m_tau") or {}
        if "value" not in me or "value" not in mm or "value" not in mt:
            return None
        me_v = float(me["value"])
        mm_v = float(mm["value"])
        mt_v = float(mt["value"])
        r1 = mm_v / me_v
        r2 = mt_v / mm_v
        tol1 = float(mm.get("tol_rel", 0.0)) + float(me.get("tol_rel", 0.0))
        tol2 = float(mt.get("tol_rel", 0.0)) + float(mm.get("tol_rel", 0.0))
        return {
            "m_mu_over_m_e": {"value": r1, "unit": "ratio", "tol_rel": tol1},
            "m_tau_over_m_mu": {"value": r2, "unit": "ratio", "tol_rel": tol2},
        }
    except Exception:
        return None


def _nu_ref_dm2_ratio(refs: dict) -> Optional[dict]:
    """Compute reference ratio (Δm^2_31 / Δm^2_21) from overlay ranges.

    Uses nu_dm21_eV2 and nu_dm31_eV2. Returns a ref dict with a conservative
    propagated range.
    """
    try:
        dm21 = refs.get("nu_dm21_eV2") or {}
        dm31 = refs.get("nu_dm31_eV2") or {}
        if "range" not in dm21 or "range" not in dm31:
            return None
        lo21, hi21 = [float(x) for x in dm21["range"]]
        lo31, hi31 = [float(x) for x in dm31["range"]]
        # ratio range: [min, max] with independent ranges
        r_lo = lo31 / hi21
        r_hi = hi31 / lo21
        # nominal value from central values if present
        v21 = float(dm21.get("value", (lo21 + hi21) / 2.0))
        v31 = float(dm31.get("value", (lo31 + hi31) / 2.0))
        return {
            "value": (v31 / v21) if v21 != 0 else None,
            "unit": "ratio",
            "range": [r_lo, r_hi],
            "note": "Derived from overlay ranges for nu_dm31_eV2 and nu_dm21_eV2.",
        }
    except Exception:
        return None

def _extract_preferred_value(core_value: dict) -> Optional[float]:
    """Try to extract a preferred scalar from common Core-index conventions."""
    if not isinstance(core_value, dict):
        return None

    # direct numeric preferred
    pref = core_value.get("preferred")
    pv = _as_float(pref)
    if pv is not None:
        return pv

    # dict preferred may use value/approx
    if isinstance(pref, dict):
        pv = _as_float(pref.get("value"))
        if pv is not None:
            return pv
        pv = _as_float(pref.get("approx"))
        if pv is not None:
            return pv

        pid = pref.get("id")
        if pid is not None and isinstance(core_value.get("candidates"), list):
            for c in core_value.get("candidates"):
                if isinstance(c, dict) and c.get("id") == pid:
                    pv = _as_float(c.get("value"))
                    if pv is not None:
                        return pv

    # special-case principal delta convention
    pv = _as_float(core_value.get("delta_principal_deg"))
    if pv is not None:
        return pv

    return None


def main() -> int:
    core_index = _pick_latest("sm29_core_index_v*.json")
    if not core_index:
        print("MISSING core index; run sm29_index_coregen.py first")
        return 2

    ref_path = _pick_overlay_ref()
    if not ref_path:
        print("MISSING overlay reference; cannot compare")
        return 3

    core = _load_json(core_index)
    refs = (_load_json(ref_path).get("refs") or {})

    def ref_keys(param: str) -> list[str]:
        p = param.strip()

        # Numeric refs
        if p.startswith("CKM vinkel 1"):
            return ["ckm_theta12_deg"]
        if p.startswith("CKM vinkel 2"):
            return ["ckm_theta23_deg"]
        if p.startswith("CKM vinkel 3"):
            return ["ckm_theta13_deg"]
        if p.startswith("CKM CP"):
            return ["ckm_delta_deg", "ckm_J"]
        if p.startswith("PMNS vinkel 1"):
            return ["pmns_theta12_deg"]
        if p.startswith("PMNS vinkel 2"):
            return ["pmns_theta23_deg"]
        if p.startswith("PMNS vinkel 3"):
            return ["pmns_theta13_deg"]
        if p.startswith("PMNS CP"):
            return ["pmns_delta_deg"]

        if "θ_QCD" in p or "theta" in p:
            return ["theta_qcd_deg"]
        if p in {"PPN γ", "PPN gamma"}:
            return ["ppn_gamma"]
        if p in {"PPN β", "PPN beta"}:
            return ["ppn_beta"]

        # Structural gates (bool refs)
        if p.startswith("Stark koppling"):
            return ["strong_proxy_gate"]
        if p.startswith("Higgs"):
            return ["higgs_struct_gate"]

        # Present but currently symbolic in Core in this branch; keep mapping for future
        if p.startswith("EM‑koppling") or p.startswith("EM-koppling"):
            return ["alpha"]
        if p.startswith("Svag koppling"):
            return ["ew_g_tree_Q0"]

        return []

    out_entries = []

    for e in (core.get("entries") or []):
        param = e.get("parameter")
        cv = e.get("core_value")

        core_deriv = str(e.get("derivation_status") or "")

        # Special-case: lepton masses are compared on dimensionless ratios.
        if str(param) in {"Elektronmassa", "Muonmassa", "Taumassa"} and isinstance(cv, dict) and cv.get("quantity") == "lepton_mass_ratios":
            lr = _lepton_ref_ratios(refs)
            details = []
            if lr and isinstance(cv.get("candidates"), list):
                # any-hit / preferred-hit across the candidate-set
                pref = cv.get("preferred")
                pref_id = pref.get("id") if isinstance(pref, dict) else pref

                for rk in ["m_mu_over_m_e", "m_tau_over_m_mu"]:
                    ref_r = lr.get(rk)
                    if not ref_r:
                        continue
                    r = {"value": ref_r["value"], "unit": "ratio", "tol_rel": ref_r["tol_rel"]}

                    ok_any = False
                    hit = None
                    cand_vals = []
                    pref_val = None
                    for c in cv.get("candidates"):
                        if not isinstance(c, dict):
                            continue
                        rp = (c.get("ratios_pred") or {}).get(rk)
                        if rp is None:
                            continue
                        rv = _as_float(rp)
                        if rv is None:
                            continue
                        cand_vals.append(rv)
                        ok, tol = _tol_ok(rv, r)
                        if ok and not ok_any:
                            ok_any = True
                            hit = rv
                        if c.get("id") == pref_id:
                            pref_val = rv
                    pref_ok = None
                    if pref_val is not None:
                        pref_ok, _ = _tol_ok(pref_val, r)

                    details.append({
                        "ref": rk,
                        "core": {"candidates": cand_vals, "hit": hit, "preferred": pref_val},
                        "ref_value": r.get("value"),
                        "ok": ok_any,
                        "any_hit": ok_any,
                        "preferred_hit": pref_ok,
                        "tol": f"tol_rel={r.get('tol_rel')}",
                        "unit": "ratio",
                        "note": "lepton mass ratio compare (overlay-only)",
                    })

            status = "UNTESTED"
            if details:
                status = _classify_status(core_deriv, details)

            out_entries.append({
                "parameter": param,
                "validation_status": status,
                "ref_keys": ["m_mu_over_m_e", "m_tau_over_m_mu"],
                "details": details,
            })
            continue

        # Special-case: neutrino masses are compared on a dimensionless Δm² ratio.
        if str(param).startswith("Neutrino") and isinstance(cv, dict) and cv.get("quantity") == "nu_mass_pattern":
            rr = _nu_ref_dm2_ratio(refs)
            details = []
            if rr and isinstance(cv.get("patterns"), list):
                pref = cv.get("preferred")
                pref_id = pref.get("id") if isinstance(pref, dict) else None
                cand_vals = []
                ok_any = False
                hit = None
                pref_val = None
                pref_ok = None
                for p in cv.get("patterns"):
                    if not isinstance(p, dict):
                        continue
                    dm = p.get("delta_m2_ratio_exact")
                    # allow nested exact dict
                    rv = None
                    if isinstance(dm, dict):
                        rv = _as_float(dm.get("value"))
                    else:
                        rv = _as_float(dm)
                    if rv is None:
                        continue
                    cand_vals.append(rv)
                    ok, _tol = _tol_ok(rv, rr)
                    if ok and not ok_any:
                        ok_any = True
                        hit = rv
                    if pref_id is not None and p.get("id") == pref_id:
                        pref_val = rv
                if pref_val is not None:
                    pref_ok, _ = _tol_ok(pref_val, rr)

                details.append({
                    "ref": "nu_dm2_ratio_31_over_21",
                    "core": {"candidates": cand_vals, "hit": hit, "preferred": pref_val},
                    "ref_value": rr.get("value"),
                    "ok": ok_any,
                    "any_hit": ok_any,
                    "preferred_hit": pref_ok,
                    "tol": f"range[{rr['range'][0]},{rr['range'][1]}]",
                    "unit": "ratio",
                    "note": "neutrino pattern compare via Δm² ratio (overlay-only)",
                })

            status = "UNTESTED"
            if details:
                status = _classify_status(core_deriv, details)

            out_entries.append({
                "parameter": param,
                "validation_status": status,
                "ref_keys": ["nu_dm31_eV2", "nu_dm21_eV2"],
                "details": details,
            })
            continue

        # Special-case: quark masses are compared on dimensionless ratio candidate-sets.
        # If QUARK_PROXY_LOCK attached a candidate-space to the Core index, we do
        # any-hit / preferred-hit honestly (preferred is facit-free).
        if str(param) in {"Up‑kvarkmassa", "Charm‑kvarkmassa", "Top‑kvarkmassa",
                          "Down‑kvarkmassa", "Strange‑kvarkmassa", "Bottom‑kvarkmassa"} and isinstance(cv, dict):
            details = []

            # Preferred path: use candidate-space from QUARK_PROXY_LOCK
            cp = cv.get("compare_proxy") if isinstance(cv, dict) else None
            if isinstance(cp, dict) and cp.get("ref_key"):
                refk = str(cp.get("ref_key"))
                ref = refs.get(refk)
                if ref:
                    cand_vals = []
                    for c in (cp.get("candidates") or []):
                        if isinstance(c, dict):
                            v = _as_float(c.get("approx"))
                            if v is not None:
                                cand_vals.append(v)

                    pref_val = None
                    pref = cp.get("preferred")
                    if isinstance(pref, dict):
                        pref_val = _as_float(pref.get("approx"))

                    hit = None
                    ok_any = False
                    for v in cand_vals:
                        ok, _ = _tol_ok(v, ref)
                        if ok:
                            ok_any = True
                            hit = v
                            break

                    pref_ok = None
                    if pref_val is not None:
                        pref_ok, _ = _tol_ok(pref_val, ref)

                    details.append({
                        "ref": refk,
                        "core": {"candidates": cand_vals, "hit": hit, "preferred": pref_val},
                        "ref_value": ref.get("value") if "value" in ref else ref.get("range"),
                        "ok": ok_any,
                        "any_hit": ok_any,
                        "preferred_hit": (pref_ok if pref_ok is not None else None),
                        "tol": _tol_ok(hit if hit is not None else (pref_val if pref_val is not None else cand_vals[0]), ref)[1] if (hit is not None or pref_val is not None or cand_vals) else "n/a",
                        "unit": ref.get("unit"),
                        "note": "quark ratio compare via QUARK_PROXY_LOCK candidate-space (overlay-only validation; no feedback)",
                    })

                status = "UNTESTED"
                if details:
                    status = _classify_status(core_deriv, details)

                out_entries.append({
                    "parameter": param,
                    "validation_status": status,
                    "ref_keys": [refk],
                    "details": details,
                })
                continue

            # Fallback: legacy direct family-ratio compare from FLAVOR_LOCK ratios.
            if isinstance(cv.get("ratios"), dict):
                qmap = {
                    # u-family
                    "Up‑kvarkmassa":      ("u", "m1_over_m2", "m_u_over_m_c", False),
                    "Charm‑kvarkmassa":   ("u", "m2_over_m3", "m_c_over_m_t", False),
                    "Top‑kvarkmassa":     ("u", "m2_over_m3", "m_t_over_m_c", True),
                    # d-family
                    "Down‑kvarkmassa":    ("d", "m1_over_m2", "m_d_over_m_s", False),
                    "Strange‑kvarkmassa": ("d", "m2_over_m3", "m_s_over_m_b", False),
                    "Bottom‑kvarkmassa":  ("d", "m2_over_m3", "m_b_over_m_s", True),
                }
                fam, field, refk, invert = qmap[str(param)]
                ref = refs.get(refk)
                if ref:
                    rv = None
                    try:
                        base = (cv.get("ratios") or {}).get(fam, {})
                        x = _as_float(base.get(field))
                        if x is not None:
                            rv = (1.0 / x) if (invert and x != 0) else x
                    except Exception:
                        rv = None
                    if rv is not None:
                        ok, tol = _tol_ok(rv, ref)
                        details.append({
                            "ref": refk,
                            "core": rv,
                            "ref_value": ref.get("value") if "value" in ref else ref.get("range"),
                            "ok": ok,
                            "any_hit": ok,
                            "preferred_hit": ok,
                            "tol": tol,
                            "unit": ref.get("unit"),
                            "note": "quark family ratio compare (legacy fallback)",
                        })

                status = "UNTESTED"
                if details:
                    status = _classify_status(core_deriv, details)

                out_entries.append({
                    "parameter": param,
                    "validation_status": status,
                    "ref_keys": [refk],
                    "details": details,
                })
                continue

        keys = ref_keys(str(param))

        status = "UNTESTED"
        details = []

        if not keys or cv is None:
            out_entries.append({
                "parameter": param,
                "validation_status": status,
                "ref_keys": keys,
                "details": details,
            })
            continue

        # CP rows store dict
        if isinstance(cv, dict) and ("delta_deg" in cv or "delta_candidates_deg" in cv or "delta_principal_deg" in cv):
            for k in keys:
                r = refs.get(k)
                if not r:
                    continue

                if k.endswith("_J") or k == "ckm_J":
                    v = _as_float(cv.get("J"))
                    if v is None:
                        continue
                    ok, tol = _tol_ok(v, r)
                    details.append({"ref": k, "core": {"candidates": [v], "hit": v, "preferred": v}, "ref_value": r.get("value"), "ok": ok, "any_hit": ok, "preferred_hit": ok, "tol": tol, "unit": r.get("unit")})
                    continue

                # delta-like: accept if ANY candidate matches
                cands = None
                if isinstance(cv.get("delta_candidates_deg"), list):
                    cands = list(cv.get("delta_candidates_deg"))
                elif "delta_principal_deg" in cv:
                    cands = [cv.get("delta_principal_deg")] + list(cv.get("delta_other_branches_deg") or [])
                elif "delta_deg" in cv:
                    cands = [cv.get("delta_deg")]
                elif "delta_deg_from_sin" in cv:
                    cands = [cv.get("delta_deg_from_sin")]

                ok_any = False
                tol_used = None
                hit = None
                for x in (cands or []):
                    xv = _as_float(x)
                    if xv is None:
                        continue
                    ok, tol = _tol_ok(xv, r)
                    tol_used = tol
                    if ok:
                        ok_any = True
                        hit = xv
                        break

                pref_v = _extract_preferred_value(cv)
                pref_ok = None
                if pref_v is not None:
                    pref_ok, _ = _tol_ok(pref_v, r)

                details.append({
                    "ref": k,
                    "core": {"candidates": cands, "hit": hit, "preferred": pref_v},
                    "ref_value": r.get("value") if "value" in r else r.get("range"),
                    "ok": ok_any,
                    "any_hit": ok_any,
                    "preferred_hit": pref_ok,
                    "tol": tol_used,
                    "unit": r.get("unit"),
                })

        # Structural compare: treat as PASS if Core entry is not BLANK and has a non-empty core_value dict
        elif isinstance(cv, dict) and any(k in keys for k in ["strong_proxy_gate", "higgs_struct_gate"]):
            for k in keys:
                r = refs.get(k)
                if not r:
                    continue
                core_gate = 1.0 if (isinstance(cv, dict) and len(cv.keys()) > 0) else 0.0
                ok, tol = _tol_ok(core_gate, r)
                details.append({
                    "ref": k,
                    "core": core_gate,
                    "ref_value": r.get("value"),
                    "ok": ok,
                    "any_hit": ok,
                    "preferred_hit": ok,
                    "tol": tol,
                    "unit": r.get("unit"),
                    "note": "structural gate (no numeric compare)",
                })

        # Scalar cv case: stored as {"value": ...}
        elif isinstance(cv, dict) and "value" in cv:
            v = _as_float(cv.get("value"))
            if v is not None:
                k = keys[0]
                r = refs.get(k)
                if r:
                    ok, tol = _tol_ok(v, r)
                    details.append({"ref": k, "core": v, "ref_value": r.get("value"), "ok": ok, "any_hit": ok, "preferred_hit": ok, "tol": tol, "unit": r.get("unit")})

        # Candidate-set scalar case: stored as {"candidates": [{"value": ...}, ...]}
        elif isinstance(cv, dict) and isinstance(cv.get("candidates"), list):
            k = keys[0]
            r = refs.get(k)
            if r:
                ok_any = False
                hit = None
                tol_used = None
                cand_vals = []
                for c in cv.get("candidates"):
                    if isinstance(c, dict):
                        xv = _as_float(c.get("value"))
                    else:
                        xv = _as_float(c)
                    if xv is None:
                        continue
                    cand_vals.append(xv)
                    ok, tol = _tol_ok(xv, r)
                    tol_used = tol
                    if ok:
                        ok_any = True
                        hit = xv
                        break

                pref_v = _extract_preferred_value(cv)
                pref_ok = None
                if pref_v is not None:
                    pref_ok, _ = _tol_ok(pref_v, r)
                details.append({
                    "ref": k,
                    "core": {"candidates": cand_vals, "hit": hit, "preferred": pref_v},
                    "ref_value": r.get("value") if "value" in r else r.get("range"),
                    "ok": ok_any,
                    "any_hit": ok_any,
                    "preferred_hit": pref_ok,
                    "tol": tol_used,
                    "unit": r.get("unit"),
                    "note": "candidate-set compare: OK if any candidate matches tolerance",
                })

        # Unknown encoding: keep UNTESTED

        if details:
            status = _classify_status(core_deriv, details)

        out_entries.append({
            "parameter": param,
            "validation_status": status,
            "ref_keys": keys,
            "details": details,
        })

    report = {
        "version": "v0.8",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "policy": {"overlay_only": True, "feeds_back": False},
        "inputs": {
            "core_index": str(core_index.relative_to(REPO)).replace("\\", "/"),
            "overlay_ref": str(ref_path.relative_to(REPO)).replace("\\", "/"),
        },
        "entries": out_entries,
    }

    out_dir = REPO / "out" / "COMPARE_SM29_INDEX"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "sm29_compare_index_v0_9.json"
    out_md = out_dir / "sm29_compare_index_v0_9.md"

    out_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# SM29 Compare Index (v0.8)",
        "",
        f"- core_index: `{report['inputs']['core_index']}`",
        f"- overlay_ref: `{report['inputs']['overlay_ref']}`",
        "",
        "| Parameter | Validation-status | Any-hit | Preferred-hit | Details |",
        "|---|---:|:---:|:---:|---|",
    ]
    for it in out_entries:
        det = it.get("details") or []
        if det:
            # aggregate
            any_list = []
            pref_list = []
            for d in det:
                any_list.append(d.get("any_hit") if d.get("any_hit") is not None else d.get("ok"))
                pref_list.append(d.get("preferred_hit"))
            any_all = all(x is True for x in any_list)
            pref_known = [x for x in pref_list if x is not None]
            pref_all = (all(x is True for x in pref_known) if pref_known else None)

            any_txt = "✓" if any_all else "✗"
            pref_txt = "✓" if pref_all is True else ("✗" if pref_all is False else "—")

            s = "; ".join([
                f"{d['ref']}: core={d.get('core')}, ref={d.get('ref_value')} (any={'OK' if (d.get('any_hit') if d.get('any_hit') is not None else d.get('ok')) else 'FAIL'}, pref={('OK' if d.get('preferred_hit') else 'FAIL') if d.get('preferred_hit') is not None else '—'}, {d.get('tol')})"
                for d in det
            ])
        else:
            any_txt = "—"
            pref_txt = "—"
            s = ""
        lines.append(f"| {it['parameter']} | {it['validation_status']} | {any_txt} | {pref_txt} | {s} |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"WROTE: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
