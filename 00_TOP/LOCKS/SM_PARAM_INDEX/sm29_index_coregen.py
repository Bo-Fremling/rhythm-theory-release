#!/usr/bin/env python3
"""SM29 index coregen (NO-FACIT).

Builds an honest map from Core artifacts:
- Derivation status: DERIVED / CANDIDATE-SET / HYP / BLANK
- Validation status: UNTESTED (Core stage only)

Writes:
  out/CORE_SM29_INDEX/sm29_core_index_v0_11.json
  out/CORE_SM29_INDEX/sm29_core_index_v0_11.md
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[3]


def _pick_latest(out_dir: Path, pattern: str) -> Optional[Path]:
    cands = sorted(out_dir.glob(pattern))
    return cands[-1] if cands else None


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _load_json(p: Path) -> dict:
    return json.loads(_read_text(p))


def _extract_sm29_names(status_md: Path) -> list[str]:
    names: list[str] = []
    for line in _read_text(status_md).splitlines():
        if not line.strip().startswith("|"):
            continue
        if "Parameter" in line and "Status" in line:
            continue
        if set(line.strip()) <= {"|", "-", " ", ":"}:
            continue
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if not parts:
            continue
        name = parts[0]
        if name and name.lower() not in {"parameter", "param"}:
            names.append(name)
    # de-dup while preserving order
    out = []
    seen = set()
    for n in names:
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def main() -> int:
    status_md = REPO / "00_TOP" / "LOCKS" / "SM_PARAM_INDEX" / "SM_29_PARAMETERS_STATUS.md"
    sm29 = _extract_sm29_names(status_md) if status_md.exists() else []

    # Core artifact presence
    # Prefer latest core artifacts when versioned.
    ew_latest = _pick_latest(REPO / "out" / "CORE_EW_COUPLING_LOCK", "ew_coupling_core_v*.json")
    em_latest = _pick_latest(REPO / "out" / "CORE_EM_LOCK", "em_lock_core_v*.json")
    gs_latest = _pick_latest(REPO / "out" / "CORE_GS_LOCK", "gs_lock_core_v*.json")
    gs_canon_latest = _pick_latest(REPO / 'out' / 'CORE_GS_CANON_DENOM_LOCK', 'gs_canon_denom_lock_core_v*.json')

    higgs_latest = _pick_latest(REPO / "out" / "CORE_HIGGS_VEV_LOCK", "higgs_vev_lock_core_v*.json")
    higgs_canon_latest = _pick_latest(REPO / 'out' / 'CORE_HIGGS_CANON_DENOM_LOCK', 'higgs_canon_denom_lock_core_v*.json')
    quark_proxy_latest = _pick_latest(REPO / "out" / "CORE_QUARK_PROXY_LOCK", "quark_proxy_core_v*.json")
    quark_proxy_reduce_latest = _pick_latest(REPO / "out" / "CORE_QUARK_PROXY_REDUCE_LOCK", "quark_proxy_reduce_core_v*.json")
    lep_cand_latest = _pick_latest(REPO / "out" / "CORE_LEPTON_MASS_LOCK", "lepton_mass_lock_core_candidates_v*.json")
    nu_latest = _pick_latest(REPO / "out" / "CORE_NU_MECHANISM_LOCK", "nu_mechanism_lock_v*.json")
    cons_latest = _pick_latest(REPO / "out" / "CORE_SM29_CONSISTENCY_LOCK", "sm29_consistency_lock_core_v*.json")

    xi_inv_latest = _pick_latest(REPO / 'out' / 'CORE_EM_XI_INVARIANT_LOCK', 'em_xi_invariant_lock_core_v*.json')

    core = {
        "EW": ew_latest if ew_latest else (REPO / "out" / "CORE_EW_COUPLING_LOCK" / "ew_coupling_core_v0_1.json"),
        "THETA": (REPO / "out" / "CORE_THETA_QCD_LOCK" / "theta_qcd_lock_v0_2.json"),
        "FLAVOR_UD": (REPO / "out" / "CORE_FLAVOR_LOCK" / "flavor_ud_core_v0_9.json"),
        "FLAVOR_ENU": (REPO / "out" / "CORE_FLAVOR_LOCK" / "flavor_enu_core_v0_9.json"),
        "FLAVOR_PP": (REPO / "out" / "CORE_FLAVOR_LOCK" / "flavor_pp_pred_core_v0_1.json"),
        "LEPTON_MASS_CAND": lep_cand_latest if lep_cand_latest else (REPO / "out" / "CORE_LEPTON_MASS_LOCK" / "lepton_mass_lock_core_candidates_v0_1.json"),
        "NU": nu_latest if nu_latest else (REPO / "out" / "CORE_NU_MECHANISM_LOCK" / "nu_mechanism_lock_v0_3.json"),
        "PPN": (REPO / "out" / "CORE_PPN_LOCK" / "ppn_lock_core_v0_1.json"),
        "EM_LOCK": em_latest if em_latest else (REPO / "out" / "CORE_EM_LOCK" / "em_lock_core_v0_2.json"),
        "GS": gs_latest if gs_latest else (REPO / "out" / "CORE_GS_LOCK" / "gs_lock_core_v0_1.json"),
        "GS_CANON": gs_canon_latest if gs_canon_latest else (REPO / 'out' / 'CORE_GS_CANON_DENOM_LOCK' / 'gs_canon_denom_lock_core_v0_1.json'),
        "HIGGS": higgs_latest if higgs_latest else (REPO / "out" / "CORE_HIGGS_VEV_LOCK" / "higgs_vev_lock_core_v0_3.json"),
        "HIGGS_CANON": higgs_canon_latest if higgs_canon_latest else (REPO / 'out' / 'CORE_HIGGS_CANON_DENOM_LOCK' / 'higgs_canon_denom_lock_core_v0_1.json'),
        "QUARK_PROXY": quark_proxy_latest if quark_proxy_latest else (REPO / "out" / "CORE_QUARK_PROXY_LOCK" / "quark_proxy_core_v0_1.json"),
        "QUARK_PROXY_REDUCED": quark_proxy_reduce_latest if quark_proxy_reduce_latest else (REPO / "out" / "CORE_QUARK_PROXY_REDUCE_LOCK" / "quark_proxy_reduce_core_v0_1.json"),
        "CONSISTENCY": cons_latest if cons_latest else (REPO / "out" / "CORE_SM29_CONSISTENCY_LOCK" / "sm29_consistency_lock_core_v0_1.json"),
        "EM_XI_INVARIANT": xi_inv_latest if xi_inv_latest else (REPO / 'out' / 'CORE_EM_XI_INVARIANT_LOCK' / 'em_xi_invariant_lock_core_v0_1.json'),
    }

    # fallback for EM_LOCK v0.1
    if not core["EM_LOCK"].exists():
        core["EM_LOCK"] = (REPO / "out" / "CORE_EM_LOCK" / "em_lock_core_v0_1.json")

    # fallback for HIGGS older files
    if not core["HIGGS"].exists():
        core["HIGGS"] = (REPO / "out" / "CORE_HIGGS_VEV_LOCK" / "higgs_vev_lock_core_v0_2.json")
    if not core["HIGGS"].exists():
        core["HIGGS"] = (REPO / "out" / "CORE_HIGGS_VEV_LOCK" / "higgs_vev_lock_core_v0_1.json")

    # consistency is optional
    if not core["CONSISTENCY"].exists():
        core["CONSISTENCY"] = (REPO / "out" / "CORE_SM29_CONSISTENCY_LOCK" / "sm29_consistency_lock_core_v0_1.json")

    def has(k: str) -> bool:
        return core[k].exists()

    # Optional cached payloads
    pp_pred = _load_json(core["FLAVOR_PP"]) if has("FLAVOR_PP") else None
    ud_full = _load_json(core["FLAVOR_UD"]) if has("FLAVOR_UD") else None
    enu_full = _load_json(core["FLAVOR_ENU"]) if has("FLAVOR_ENU") else None
    ckm_raw = (ud_full or {}).get("CKM") if isinstance(ud_full, dict) else None
    pmns_raw = (enu_full or {}).get("PMNS") if isinstance(enu_full, dict) else None
    ppn_raw = _load_json(core["PPN"]) if has("PPN") else None

    em_full = _load_json(core["EM_LOCK"]) if has("EM_LOCK") else None
    ew_full = _load_json(core["EW"]) if has("EW") else None
    gs_full = _load_json(core["GS"]) if has("GS") else None
    gs_canon_full = _load_json(core['GS_CANON']) if has('GS_CANON') else None
    higgs_full = _load_json(core["HIGGS"]) if has("HIGGS") else None
    higgs_canon_full = _load_json(core['HIGGS_CANON']) if has('HIGGS_CANON') else None
    quark_proxy_full = _load_json(core["QUARK_PROXY"]) if has("QUARK_PROXY") else None
    quark_proxy_reduced_full = _load_json(core["QUARK_PROXY_REDUCED"]) if has("QUARK_PROXY_REDUCED") else None
    lep_cand_full = _load_json(core["LEPTON_MASS_CAND"]) if has("LEPTON_MASS_CAND") else None
    nu_full = _load_json(core["NU"]) if has("NU") else None
    cons_full = _load_json(core["CONSISTENCY"]) if has("CONSISTENCY") else None

    inv_full = _load_json(core['EM_XI_INVARIANT']) if has('EM_XI_INVARIANT') else None

    # Promotion gate (facit-free): alpha_RT can be promoted to DERIVED only when
    # (i) SM29_CONSISTENCY_LOCK reduced alpha_RT to a singleton and
    # (ii) EM_XI_INVARIANT_LOCK provides the duty-factor proof artifact.
    red_alpha0 = None
    if isinstance(cons_full, dict):
        red_alpha0 = ((cons_full.get('reduced') or {}).get('alpha_RT'))
    alpha_singleton = bool(isinstance(red_alpha0, dict) and int(red_alpha0.get('kept') or 0) == 1 and isinstance(red_alpha0.get('candidates'), list) and len(red_alpha0.get('candidates')) == 1)

    xi_inv_ok = bool(isinstance(inv_full, dict) and str(inv_full.get('derivation_status')) == 'DERIVED' and isinstance(inv_full.get('duty_factor'), dict) and str(inv_full.get('duty_factor', {}).get('expr')) == '20/21')

    alpha_promote_ok = bool(alpha_singleton and xi_inv_ok)

    red_g0 = None
    if isinstance(cons_full, dict):
        red_g0 = ((cons_full.get('reduced') or {}).get('g_weak'))
    g_singleton = bool(isinstance(red_g0, dict) and int(red_g0.get('kept') or 0) == 1 and isinstance(red_g0.get('candidates'), list) and len(red_g0.get('candidates')) == 1)
    g_promote_ok = bool(alpha_promote_ok and g_singleton)

    def _top(cands: list[dict], n: int = 6, *, keep_keys: list[str] | None = None) -> list[dict]:
        kk = keep_keys or ["id", "expr", "approx", "family", "complexity", "parents", "source_alpha_s_id"]
        out = []
        for c in cands[: max(0, int(n))]:
            if isinstance(c, dict):
                out.append({k: c.get(k) for k in kk if k in c})
        return out

    def _angles(which: str) -> Optional[dict]:
        if pp_pred and isinstance(pp_pred, dict):
            block = pp_pred.get(which)
            if isinstance(block, dict):
                ang = block.get("angles")
                return ang if isinstance(ang, dict) else None
        # fallback to raw
        if which == "CKM" and isinstance(ckm_raw, dict):
            ang = ckm_raw.get("angles")
            return ang if isinstance(ang, dict) else None
        if which == "PMNS" and isinstance(pmns_raw, dict):
            ang = pmns_raw.get("angles")
            return ang if isinstance(ang, dict) else None
        return None

    # Map to statuses
    entries = []
    for name in sm29:
        dstat = "BLANK"
        vstat = "UNTESTED"
        source = None
        artifact = None
        core_value = None
        note = None
        scope = "FULL_CORE"
        if isinstance(name, str) and name.strip().startswith("κ"):
            scope = "OVERLAY_ONLY"

        # --- EW
        if name.strip() in {"sin^2θ_W", "sin^2 theta_W", "sin²θ_W"}:
            if has("EW"):
                dstat = "DERIVED"
                source = "EW_COUPLING_LOCK"
                artifact = str(core["EW"].relative_to(REPO)).replace("\\", "/")
                core_value = {"value": 0.25, "unit": "dimensionless"}
        # --- theta_QCD
        elif name.strip() in {"Stark CP‑vinkel (θ_QCD)", "θ_QCD", "theta_QCD", "θQCD"}:
            if has("THETA"):
                dstat = "DERIVED"
                source = "THETA_QCD_LOCK"
                artifact = str(core["THETA"].relative_to(REPO)).replace("\\", "/")
                core_value = {"value": 0.0, "unit": "deg"}
        # --- CKM rows
        elif name.startswith("CKM"):
            ang = _angles("CKM")
            if ang:
                dstat = "DERIVED" if has("FLAVOR_PP") else "CANDIDATE-SET"
                source = "FLAVOR_LOCK"
                artifact = str((core["FLAVOR_PP"] if has("FLAVOR_PP") else core["FLAVOR_UD"]).relative_to(REPO)).replace("\\", "/")
                if "vinkel 1" in name:
                    core_value = {"value": float(ang.get("theta12_deg")), "unit": "deg"}
                elif "vinkel 2" in name:
                    core_value = {"value": float(ang.get("theta23_deg")), "unit": "deg"}
                elif "vinkel 3" in name:
                    core_value = {"value": float(ang.get("theta13_deg")), "unit": "deg"}
                elif "CP" in name or "fas" in name:
                    # CP-phase is ambiguous from sinδ alone; emit all sin-consistent branches and
                    # pick a deterministic principal branch without any facit.
                    d0 = float(ang.get("delta_deg_from_sin")) if ang.get("delta_deg_from_sin") is not None else None
                    branches = None
                    principal = None
                    other = None
                    if d0 is not None:
                        raw = [d0, 180.0 - d0, 180.0 + d0, 360.0 - d0]
                        norm = [((x % 360.0) + 360.0) % 360.0 for x in raw]
                        seen = set()
                        branches = []
                        for x in norm:
                            key = round(float(x), 12)
                            if key in seen:
                                continue
                            seen.add(key)
                            branches.append(float(x))

                        # Deterministic tie-break (facit-free): choose the smallest δ in [0,180].
                        principal = min(branches, key=lambda x: (0 if x <= 180.0 else 1, x))
                        pk = round(principal, 12)
                        other = [x for x in branches if round(x, 12) != pk]

                    core_value = {
                        "delta_candidates_deg": branches,
                        "delta_principal_deg": principal,
                        "delta_other_branches_deg": other,
                        "preferred": principal,
                        "J": float(ang.get("J")) if ang.get("J") is not None else None,
                        "unit": {"delta": "deg", "J": "dimensionless"},
                        "note": "Tie-break is internal: choose smallest δ in [0,180] among sin-consistent branches; other branches emitted; no facit used.",
                    }
        # --- PMNS rows
        elif name.startswith("PMNS"):
            ang = _angles("PMNS")
            if ang:
                dstat = "DERIVED" if has("FLAVOR_PP") else "CANDIDATE-SET"
                source = "FLAVOR_LOCK"
                artifact = str((core["FLAVOR_PP"] if has("FLAVOR_PP") else core["FLAVOR_ENU"]).relative_to(REPO)).replace("\\", "/")
                if "vinkel 1" in name:
                    core_value = {"value": float(ang.get("theta12_deg")), "unit": "deg"}
                elif "vinkel 2" in name:
                    core_value = {"value": float(ang.get("theta23_deg")), "unit": "deg"}
                elif "vinkel 3" in name:
                    core_value = {"value": float(ang.get("theta13_deg")), "unit": "deg"}
                elif "CP" in name or "fas" in name:
                    # Deterministic tie-break (facit-free): choose the branch closest to π (180°)
                    # among the sin-consistent branches. This is a convention consistent with A/B symmetry.
                    # We still emit other branches for transparency.
                    dstat = "DERIVED"
                    d0 = float(ang.get("delta_deg_from_sin")) if ang.get("delta_deg_from_sin") is not None else None
                    branches = None
                    principal = None
                    if d0 is not None:
                        raw = [d0, 180.0 - d0, 180.0 + d0, 360.0 - d0]
                        norm = [((x % 360.0) + 360.0) % 360.0 for x in raw]
                        seen = set()
                        branches = []
                        for x in norm:
                            key = round(float(x), 12)
                            if key in seen:
                                continue
                            seen.add(key)
                            branches.append(float(x))

                        def dist_pi(x: float) -> float:
                            # shortest distance on circle to 180°
                            return abs(((x - 180.0 + 180.0) % 360.0) - 180.0)

                        # tie-break: closest to π, then prefer >=180, then smaller value
                        principal = min(branches, key=lambda x: (dist_pi(x), 0 if x >= 180.0 else 1, x))

                    other = None
                    if branches is not None and principal is not None:
                        pk = round(principal, 12)
                        other = [x for x in branches if round(x, 12) != pk]

                    core_value = {
                        "delta_principal_deg": principal,
                        "delta_other_branches_deg": other,
                        "J": float(ang.get("J")) if ang.get("J") is not None else None,
                        "unit": {"delta": "deg", "J": "dimensionless"},
                        "note": "Tie-break is internal: choose δ branch nearest π (180°); other branches emitted for transparency; no facit used.",
                    }
        # --- lepton masses (ratios only)
        elif name in {"Elektronmassa", "Muonmassa", "Taumassa", "m_e", "m_μ", "m_τ", "m_mu", "m_tau"}:
            scope = "RATIO_ONLY_OVERLAY_ANCHOR"
            # Optional reduction via SM29_CONSISTENCY_LOCK (facit-free):
            red_lep = None
            if isinstance(cons_full, dict):
                red_lep = ((cons_full.get("reduced") or {}).get("lepton_mass_ratios"))

            lep_block = None
            if isinstance(red_lep, dict) and isinstance(red_lep.get("candidates"), list) and len(red_lep.get("candidates")) >= 1:
                lep_block = {
                    "candidates": red_lep.get("candidates"),
                    "preferred": red_lep.get("preferred"),
                    "kept": int(red_lep.get("kept") or len(red_lep.get("candidates"))),
                    "meta": red_lep.get("meta"),
                    "artifact": str(core["CONSISTENCY"].relative_to(REPO)).replace("\\", "/"),
                }

            if lep_block is not None:
                # If reduced to a singleton under a Core-semantic rule, promote ratios to DERIVED.
                dstat = "DERIVED" if lep_block.get("kept") == 1 else "CANDIDATE-SET"
                source = "SM29_CONSISTENCY_LOCK"
                artifact = lep_block.get("artifact")
                cands = lep_block.get("candidates")
                pref = lep_block.get("preferred")
                core_value = {
                    "type": "finite_candidate_set",
                    "quantity": "lepton_mass_ratios",
                    "candidates": [
                        {"id": c.get("id"), "artifact": c.get("artifact"), "ratios_pred": c.get("ratios_pred"), "policy_complexity": c.get("policy_complexity")}
                        for c in cands if isinstance(c, dict)
                    ],
                    "preferred": pref if isinstance(pref, dict) else None,
                    "note": "Reduced via SM29_CONSISTENCY_LOCK (arming rule when cap present). Ratios only; absolute masses remain overlay-only.",
                    "meta": lep_block.get("meta"),
                }
                note = "Core lepton ratio set reduced by consistency lock (facit-free)."
            elif isinstance(lep_cand_full, dict) and isinstance(lep_cand_full.get("candidates"), list):

                dstat = "CANDIDATE-SET"
                source = "LEPTON_MASS_LOCK"
                artifact = str(core["LEPTON_MASS_CAND"].relative_to(REPO)).replace("\\", "/")
                cands = lep_cand_full.get("candidates")
                pref = (lep_cand_full.get("tie_break") or {}).get("preferred")
                core_value = {
                    "type": "finite_candidate_set",
                    "quantity": "lepton_mass_ratios",
                    "candidates": [
                        {"id": c.get("id"), "artifact": c.get("artifact"), "ratios_pred": c.get("ratios_pred"), "policy_complexity": c.get("policy_complexity")}
                        for c in cands if isinstance(c, dict)
                    ],
                    "preferred": pref if isinstance(pref, dict) else None,
                    "note": "Ratios only; absolute masses require an overlay anchor. Preferred is min-complexity only (no facit).",
                }
                note = "Core provides only lepton mass ratios (finite candidate-set). Absolute mass scale is overlay-only."
        # --- quark masses (ratios/proxy only; absolute needs one anchor per family)
        elif "kvarkmassa" in name or "quark" in name:
            scope = "PROXY_RATIO_ONLY_OVERLAY_ANCHOR"
            if has("FLAVOR_UD"):
                dstat = "CANDIDATE-SET"
                source = "FLAVOR_LOCK"
                artifact = str(core["FLAVOR_UD"].relative_to(REPO)).replace("\\", "/")
                if isinstance(ud_full, dict) and isinstance(ud_full.get("u"), dict) and isinstance(ud_full.get("d"), dict):
                    u = ud_full.get("u")
                    d = ud_full.get("d")
                    um = u.get("masses") if isinstance(u, dict) else None
                    dm = d.get("masses") if isinstance(d, dict) else None
                    ratios_u = u.get("ratios") if isinstance(u, dict) else None
                    ratios_d = d.get("ratios") if isinstance(d, dict) else None
                    choice = {"u": u.get("choice"), "d": d.get("choice"), "cost": ud_full.get("cost")}
                    # Map parameter name -> proxy component.
                    # NOTE: Avoid single-letter substring traps (e.g. 'Strange' contains 't', 'Bottom' contains 'd').
                    proxy = None
                    family = None
                    n = name.lower() if isinstance(name, str) else str(name).lower()

                    if "up" in n:
                        proxy = um[0] if isinstance(um, list) and len(um) >= 1 else None
                        family = "u"
                    elif "charm" in n:
                        proxy = um[1] if isinstance(um, list) and len(um) >= 2 else None
                        family = "u"
                    elif ("topp" in n) or ("top" in n):
                        proxy = um[2] if isinstance(um, list) and len(um) >= 3 else None
                        family = "u"
                    elif "down" in n:
                        proxy = dm[0] if isinstance(dm, list) and len(dm) >= 1 else None
                        family = "d"
                    elif "strange" in n:
                        proxy = dm[1] if isinstance(dm, list) and len(dm) >= 2 else None
                        family = "d"
                    elif "bottom" in n:
                        proxy = dm[2] if isinstance(dm, list) and len(dm) >= 3 else None
                        family = "d"

                    core_value = {
                        "type": "proxy_mass_component",
                        "unit": "dimensionless_proxy",
                        "value": float(proxy) if proxy is not None else None,
                        "family": family,
                        "triplet": {"u/c/t": um, "d/s/b": dm},
                        "ratios": {"u": ratios_u, "d": ratios_d},
                        "compare_proxy": None,
                        "choice": choice,
                        "note": "Proxy masses are Core-internal (no κ). Absolute masses are overlay-only.",
                    }

                    # Attach a facit-free ratio candidate-set (if available) so compare can
                    # report any-hit vs preferred-hit without influencing Core selection.
                    # Source is Core-only: QUARK_PROXY_LOCK (candidate-space) or QUARK_PROXY_REDUCE_LOCK (singleton reduction).
                    cs = {}
                    src_q = None
                    src_name = None
                    if isinstance(quark_proxy_reduced_full, dict):
                        cs = (quark_proxy_reduced_full.get("reduced_candidate_space") or {})
                        src_q = str(core["QUARK_PROXY_REDUCED"].relative_to(REPO)).replace("\\", "/")
                        src_name = "QUARK_PROXY_REDUCE_LOCK"
                    elif isinstance(quark_proxy_full, dict):
                        cs = (quark_proxy_full.get("candidate_space") or {})
                        src_q = str(core["QUARK_PROXY"].relative_to(REPO)).replace("\\", "/")
                        src_name = "QUARK_PROXY_LOCK"

                    def _inv_block(block: dict) -> dict:
                        # Invert each candidate approx; preferred inverted likewise.
                        cands = []
                        for c in (block.get("candidates") or []):
                            if not isinstance(c, dict):
                                continue
                            v = c.get("approx")
                            try:
                                fv = float(v)
                            except Exception:
                                continue
                            if fv == 0:
                                continue
                            c2 = dict(c)
                            c2["approx"] = 1.0 / fv
                            c2["expr"] = f"1/({c.get('expr')})"
                            cands.append(c2)
                        pref = block.get("preferred")
                        pref2 = None
                        if isinstance(pref, dict):
                            try:
                                pv = float(pref.get("approx"))
                                if pv != 0:
                                    pref2 = dict(pref)
                                    pref2["approx"] = 1.0 / pv
                                    pref2["expr"] = f"1/({pref.get('expr')})"
                            except Exception:
                                pref2 = None
                        return {"type": block.get("type"), "base": block.get("base"), "candidates": cands, "preferred": pref2}

                    if isinstance(cs, dict) and cs and src_name and src_q:
                        # Decide which ratio ref key this parameter uses.
                        ref_key = None
                        block = None
                        invert = False
                        if family == "u" and "up" in n:
                            ref_key = "m_u_over_m_c"
                            block = cs.get(ref_key)
                        elif family == "u" and "charm" in n:
                            ref_key = "m_c_over_m_t"
                            block = cs.get(ref_key)
                        elif family == "u" and ("topp" in n or "top" in n):
                            ref_key = "m_t_over_m_c"
                            block = cs.get("m_c_over_m_t")
                            invert = True
                        elif family == "d" and "down" in n:
                            ref_key = "m_d_over_m_s"
                            block = cs.get(ref_key)
                        elif family == "d" and "strange" in n:
                            ref_key = "m_s_over_m_b"
                            block = cs.get(ref_key)
                        elif family == "d" and "bottom" in n:
                            ref_key = "m_b_over_m_s"
                            block = cs.get("m_s_over_m_b")
                            invert = True

                        if isinstance(block, dict) and ref_key:
                            use_block = _inv_block(block) if invert else block
                            core_value["compare_proxy"] = {
                                "ref_key": ref_key,
                                "source": src_name,
                                "artifact": src_q,
                                "candidates": _top(use_block.get("candidates") or [], n=24, keep_keys=["id", "expr", "approx", "p", "d"]),
                                "preferred": use_block.get("preferred"),
                                "note": "Candidate-space r^p/d with p,d in {1..6}; preferred is facit-free. Reduced lock keeps preferred only.",
                            }

                            # Promote this parameter to DERIVED if candidate-space is a singleton after reduction.
                            cands = core_value.get("compare_proxy", {}).get("candidates") or []
                            if src_name == "QUARK_PROXY_REDUCE_LOCK" and isinstance(cands, list) and len(cands) == 1:
                                dstat = "DERIVED"
                                source = "QUARK_PROXY_REDUCE_LOCK"
                                artifact = src_q
                                note = "Quark ratio proxies reduced to singleton by QUARK_PROXY_REDUCE_LOCK (facit-free; derived from FLAVOR_LOCK metadata). Absolute mass scale remains overlay-only."
                note = note or "Core provides relative mass proxies (u/c/t and d/s/b) + ratios; absolute mass scale is overlay-only."
        # --- neutrino pattern
        elif name.startswith("Neutrino") or "Δm" in name or "dm" in name:
            scope = "RATIO_ONLY_OVERLAY_ANCHOR"
            if isinstance(nu_full, dict) and isinstance((nu_full.get("results") or {}).get("patterns"), list):
                # Optional reduction via SM29_CONSISTENCY_LOCK (facit-free):
                red_nu = None
                if isinstance(cons_full, dict):
                    red_nu = ((cons_full.get("reduced") or {}).get("nu_patterns"))

                use_red = isinstance(red_nu, dict) and isinstance(red_nu.get("patterns"), list) and len(red_nu.get("patterns")) >= 1

                if use_red:
                    patterns = red_nu.get("patterns")
                    pref = red_nu.get("preferred")
                    kept = int(red_nu.get("kept") or len(patterns))
                    dstat = "DERIVED" if (kept == 1 and isinstance(pref, dict) and pref.get("pattern_status") == "DERIVED") else "CANDIDATE-SET"
                    source = "SM29_CONSISTENCY_LOCK"
                    artifact = str(core["CONSISTENCY"].relative_to(REPO)).replace("\\", "/")
                    meta = red_nu.get("meta")
                    note = "Core neutrino pattern set reduced by SM29_CONSISTENCY_LOCK (facit-free)."
                else:
                    dstat = "CANDIDATE-SET"
                    source = "NU_MECHANISM_LOCK"
                    artifact = str(core["NU"].relative_to(REPO)).replace("\\", "/")
                    res = nu_full.get("results") or {}
                    patterns = res.get("patterns")
                    sel = res.get("selection")
                    pref_id = sel.get("preferred_pattern_id") if isinstance(sel, dict) else None
                    pref = None
                    if isinstance(patterns, list) and pref_id is not None:
                        for p in patterns:
                            if isinstance(p, dict) and p.get("id") == pref_id:
                                pref = {k: p.get(k) for k in ["id", "n", "m_over_m_e", "delta_m2_ratio_exact", "note", "pattern_status"]}
                                break
                    meta = None
                    note = "Core provides only neutrino mass-pattern ratios (finite candidate-set). Absolute masses are overlay-only."

                core_value = {
                    "type": "finite_candidate_set",
                    "quantity": "nu_mass_pattern",
                    "patterns": [
                        {k: p.get(k) for k in ["id", "n", "m_over_m_e", "delta_m2_ratio_exact", "note", "pattern_status"]}
                        for p in (patterns if isinstance(patterns, list) else []) if isinstance(p, dict)
                    ],
                    "preferred": pref if isinstance(pref, dict) else None,
                    "note": "Ratios only; absolute neutrino masses require an overlay anchor. Preferred is Core-internal.",
                    "meta": meta,
                }
        # --- PPN gamma/beta
        elif name.strip() in {"PPN γ", "PPN beta", "PPN β"}:
            if has("PPN") and isinstance(ppn_raw, dict):
                dstat = "DERIVED"
                source = "PPN_LOCK"
                artifact = str(core["PPN"].relative_to(REPO)).replace("\\", "/")
                if "γ" in name:
                    core_value = {"value": float(ppn_raw.get("ppn_gamma")), "unit": "dimensionless"}
                elif "β" in name or "beta" in name:
                    core_value = {"value": float(ppn_raw.get("ppn_beta")), "unit": "dimensionless"}
        # --- Higgs (symbolic boundary)
        elif "Higgs" in name and ("massa" in name or "mass" in name):
            # Prefer canon-denom reduction if present (facit-free).
            hc_path = core.get("HIGGS_CANON")
            hc = higgs_canon_full if isinstance(higgs_canon_full, dict) else None
            if hc_path and hc_path.exists() and isinstance(hc, dict) and str(hc.get("derivation_status")) == "DERIVED":
                dstat = "DERIVED"
                source = "HIGGS_CANON_DENOM_LOCK"
                artifact = str(hc_path.relative_to(REPO)).replace("\\", "/")

                red = hc.get("reduced") if isinstance(hc, dict) else None
                red = red if isinstance(red, dict) else {}
                mblk = red.get("mH_hat") if isinstance(red.get("mH_hat"), dict) else {}
                vblk = red.get("v_hat") if isinstance(red.get("v_hat"), dict) else {}
                lblk = red.get("lambda_H") if isinstance(red.get("lambda_H"), dict) else {}

                m_pref = mblk.get("preferred") if isinstance(mblk, dict) else None
                v_pref = vblk.get("preferred") if isinstance(vblk, dict) else None
                l_pref = lblk.get("preferred") if isinstance(lblk, dict) else None

                core_value = {
                    "value": 1.0,
                    "gate": "PASS_STRUCT",
                    "symbol": "mH_RT := mH_hat/Tick",
                    "proxy": "mH_hat := sqrt(2*lambda_H)*v_hat",
                    "candidate_count": int(mblk.get("candidate_count")) if isinstance(mblk.get("candidate_count"), int) else 1,
                    "preferred": m_pref if isinstance(m_pref, dict) else None,
                    "selected": {
                        "v_hat": v_pref if isinstance(v_pref, dict) else None,
                        "lambda_H": l_pref if isinstance(l_pref, dict) else None,
                    },
                    "unit": "tick^-1 (RT units) via Tick (symbolic)",
                }
                note = "Core Higgs mass promoted to DERIVED by canon denom (v_hat=1/30) + canon quartic (lambda_H=1). Tick remains symbolic."
            else:
                # Fallback: boundary candidate-set (HIGGS_VEV_LOCK)
                h_path = core.get("HIGGS")
                h = higgs_full if isinstance(higgs_full, dict) else None
                if h_path and h_path.exists() and isinstance(h, dict):
                    has_mhat = False
                    cs = h.get("candidate_space") if isinstance(h, dict) else None
                    if isinstance(cs, dict) and isinstance(cs.get("mH_hat"), dict):
                        cands = cs.get("mH_hat", {}).get("candidates")
                        has_mhat = isinstance(cands, list) and len(cands) > 0

                    dstat = "CANDIDATE-SET" if has_mhat else "HYP"
                    source = "HIGGS_VEV_LOCK"
                    artifact = str(h_path.relative_to(REPO)).replace("\\", "/")
                    if has_mhat:
                        mhat_blk = (h.get("candidate_space") or {}).get("mH_hat") or {}
                        mhat_c = mhat_blk.get("candidates") if isinstance(mhat_blk, dict) else None
                        mhat_pref = mhat_blk.get("preferred") if isinstance(mhat_blk, dict) else None
                        core_value = {
                            "value": 1.0,
                            "gate": "PASS_STRUCT",
                            "symbol": "mH_RT := mH_hat/Tick",
                            "proxy": "mH_hat := sqrt(2*lambda_H)*v_hat",
                            "candidate_count": len(mhat_c) if isinstance(mhat_c, list) else None,
                            "preferred": mhat_pref if isinstance(mhat_pref, dict) else None,
                            "candidates_top": _top(mhat_c, n=6) if isinstance(mhat_c, list) else None,
                            "unit": "tick^-1 (RT units) via Tick (symbolic)",
                        }
                        note = "Core Higgs mass is a finite candidate-set via mH_hat (dimensionless proxy); no facit selection. SI mapping is overlay-only."
                    else:
                        core_value = {"symbol": "mH_RT := sqrt(2*lambda_H)*v_RT", "unit": "tick^-1 (RT units)"}
                        note = "Core Higgs mass is symbolic until mH_hat (or v_hat+lambda_H) is promoted to a finite candidate-set."
                else:
                    dstat = "BLANK"
                    note = "HIGGS_VEV_LOCK core artifact not generated yet."
        elif "Higgs" in name and ("VEV" in name or "(v" in name or "v)" in name):
            # Prefer canon-denom reduction if present (facit-free).
            hc_path = core.get("HIGGS_CANON")
            hc = higgs_canon_full if isinstance(higgs_canon_full, dict) else None
            if hc_path and hc_path.exists() and isinstance(hc, dict) and str(hc.get("derivation_status")) == "DERIVED":
                dstat = "DERIVED"
                source = "HIGGS_CANON_DENOM_LOCK"
                artifact = str(hc_path.relative_to(REPO)).replace("\\", "/")

                red = hc.get("reduced") if isinstance(hc, dict) else None
                red = red if isinstance(red, dict) else {}
                vblk = red.get("v_hat") if isinstance(red.get("v_hat"), dict) else {}
                v_pref = vblk.get("preferred") if isinstance(vblk, dict) else None

                core_value = {
                    "value": 1.0,
                    "gate": "PASS_STRUCT",
                    "symbol": "v_RT := v_hat/Tick",
                    "unit": "tick^-1 (RT units)",
                    "proxy": "v_hat",
                    "candidate_count": int(vblk.get("candidate_count")) if isinstance(vblk.get("candidate_count"), int) else 1,
                    "preferred": v_pref if isinstance(v_pref, dict) else None,
                }
                note = "Core Higgs VEV promoted to DERIVED by canon denom (v_hat=1/30). Tick remains symbolic."
            else:
                # Fallback: boundary candidate-set (HIGGS_VEV_LOCK)
                h_path = core.get("HIGGS")
                h = higgs_full if isinstance(higgs_full, dict) else None
                if h_path and h_path.exists() and isinstance(h, dict):
                    h_kind = (h or {}).get("derivation_status") if isinstance(h, dict) else None
                    dstat = "CANDIDATE-SET" if h_kind == "CANDIDATE-SET" else "HYP"
                    source = "HIGGS_VEV_LOCK"
                    artifact = str(h_path.relative_to(REPO)).replace("\\", "/")
                    vhat_blk = (h.get("candidate_space") or {}).get("v_hat") or {}
                    vhat_c = vhat_blk.get("candidates") if isinstance(vhat_blk, dict) else None
                    vhat_pref = vhat_blk.get("preferred") if isinstance(vhat_blk, dict) else None
                    core_value = {
                        "value": 1.0,
                        "gate": "PASS_STRUCT",
                        "symbol": "v_RT := v_hat/Tick",
                        "unit": "tick^-1 (RT units)",
                        "proxy": "v_hat",
                        "candidate_count": len(vhat_c) if isinstance(vhat_c, list) else None,
                        "preferred": vhat_pref if isinstance(vhat_pref, dict) else None,
                        "candidates_top": _top(vhat_c, n=6) if isinstance(vhat_c, list) else None,
                    }
                    note = "Core Higgs VEV boundary: v_hat is a finite candidate-set (no facit selection); preferred is min complexity; v_RT stays symbolic via Tick."
                else:
                    dstat = "BLANK"
                    note = "HIGGS_VEV_LOCK core artifact not generated yet."
# --- alpha, g, g_s and others
        elif "α" in name or "alpha" in name:
            # Prefer SM29_CONSISTENCY_LOCK reduction for alpha_RT (facit-free).
            red = None
            if isinstance(cons_full, dict):
                red = ((cons_full.get("reduced") or {}).get("alpha_RT"))

            if isinstance(red, dict) and isinstance(red.get("candidates"), list) and len(red.get("candidates")) > 0:
                # Effective candidate set = reduced candidates.
                dstat = "DERIVED" if alpha_promote_ok else "CANDIDATE-SET"
                source = "SM29_CONSISTENCY_LOCK" + (" + EM_XI_INVARIANT_LOCK" if xi_inv_ok else "")
                art1 = str(core["CONSISTENCY"].relative_to(REPO)).replace("\\", "/")
                art2 = str(core["EM_XI_INVARIANT"].relative_to(REPO)).replace("\\", "/") if has("EM_XI_INVARIANT") and core.get("EM_XI_INVARIANT") else None
                artifact = art1 + (("," + art2) if art2 else "")

                red_c = [c for c in (red.get("candidates") or []) if isinstance(c, dict)]
                pref = red.get("preferred") if isinstance(red.get("preferred"), dict) else None

                core_value = {
                    "type": "finite_candidate_set",
                    "quantity": "alpha_RT",
                    "unit": "dimensionless",
                    "symbol": "alpha_RT := Xi_RT/2",
                    "candidates": [
                        {"id": c.get("id"), "expr": c.get("expr"), "value": c.get("approx")}
                        for c in red_c
                    ],
                    "preferred": pref,
                    "candidate_count": len(red_c),
                    "candidates_full_count": int(red.get("candidate_count") or len(red_c)),
                    "kept": int(red.get("kept") or len(red_c)),
                    "reduction_meta": red.get("meta"),
                    "invariants": (inv_full.get("duty_factor") if xi_inv_ok and isinstance(inv_full, dict) else None),
                    "promotion_rule": "DERIVED iff (kept==1) and EM_XI_INVARIANT_LOCK(duty=20/21, DERIVED)",
                }
                note = "Core alpha_RT reduced by SM29_CONSISTENCY_LOCK; promoted to DERIVED only when duty-factor invariant is present (facit-free)."
            else:
                # Fallback to EM_LOCK candidate-space (older/aux path)
                em_path = core.get("EM_LOCK")
                em = em_full if isinstance(em_full, dict) else None
                if em_path and em_path.exists() and isinstance(em, dict):
                    if isinstance(em, dict) and em.get("derivation_status") in {"HYP", "DERIVED", "CANDIDATE-SET"}:
                        dstat = "CANDIDATE-SET" if em.get("derivation_status") == "CANDIDATE-SET" else "HYP"
                        source = "EM_LOCK"
                        artifact = str(em_path.relative_to(REPO)).replace("\\", "/")
                        cs = (em.get("candidate_space") or {}) if isinstance(em, dict) else {}
                        a_cs = cs.get("alpha_RT") if isinstance(cs, dict) else None
                        a_cands = a_cs.get("candidates") if isinstance(a_cs, dict) else None
                        a_pref = a_cs.get("preferred") if isinstance(a_cs, dict) else None
                        if isinstance(a_cands, list) and len(a_cands) > 0:
                            core_value = {
                                "candidates": [
                                    {"id": c.get("id"), "expr": c.get("expr"), "value": c.get("approx")}
                                    for c in a_cands if isinstance(c, dict)
                                ],
                                "preferred": a_pref,
                                "unit": "dimensionless",
                                "symbol": "alpha_RT := Xi_RT/2",
                                "candidate_count": len(a_cands),
                            }
                            note = "Fallback: Core alpha_RT from EM_LOCK candidate space (no consistency reduction)."
                        else:
                            core_value = {"symbol": "alpha_RT := Xi_RT/2", "unit": "dimensionless"}
                            note = "Fallback: EM_LOCK exists but did not emit alpha_RT candidates."
                    else:
                        dstat = "BLANK"
                        note = "Core EM_LOCK artifact unreadable/invalid; alpha remains BLANK."
                else:
                    dstat = "BLANK"
                    note = "Core EM_LOCK not generated yet; alpha remains BLANK."

        elif name.strip().startswith("Svag koppling") or name.strip() in {"g", "g_weak"}:
            # Prefer SM29_CONSISTENCY_LOCK reduction for g_weak (facit-free; inherits alpha_RT reduction).
            redg = None
            if isinstance(cons_full, dict):
                redg = ((cons_full.get("reduced") or {}).get("g_weak"))

            if isinstance(redg, dict) and isinstance(redg.get("candidates"), list) and len(redg.get("candidates")) > 0:
                dstat = "DERIVED" if g_promote_ok else "CANDIDATE-SET"
                source = "SM29_CONSISTENCY_LOCK" + (" + EM_XI_INVARIANT_LOCK" if xi_inv_ok else "")
                art1 = str(core["CONSISTENCY"].relative_to(REPO)).replace("\\", "/")
                art2 = str(core["EM_XI_INVARIANT"].relative_to(REPO)).replace("\\", "/") if has("EM_XI_INVARIANT") and core.get("EM_XI_INVARIANT") else None
                artifact = art1 + (("," + art2) if art2 else "")

                red_c = [c for c in (redg.get("candidates") or []) if isinstance(c, dict)]
                pref = redg.get("preferred") if isinstance(redg.get("preferred"), dict) else None

                core_value = {
                    "type": "finite_candidate_set",
                    "quantity": "g_weak",
                    "unit": "dimensionless",
                    "relation": "g = 4*sqrt(pi*alpha_RT) (since sin^2(theta_W)=1/4)",
                    "candidates": [
                        {"id": c.get("id"), "expr": c.get("expr"), "value": c.get("approx")}
                        for c in red_c
                    ],
                    "preferred": pref,
                    "candidate_count": len(red_c),
                    "candidates_full_count": int(redg.get("candidate_count") or len(red_c)),
                    "kept": int(redg.get("kept") or len(red_c)),
                    "reduction_meta": redg.get("meta"),
                    "invariants": (inv_full.get("duty_factor") if xi_inv_ok and isinstance(inv_full, dict) else None),
                    "promotion_rule": "DERIVED iff alpha_RT is DERIVED (duty invariant present) and kept==1",
                }
                note = "Core g_weak reduced by SM29_CONSISTENCY_LOCK; promoted to DERIVED only when alpha_RT is DERIVED (facit-free)."
            else:
                # Fallback to EW lock candidate-set representation.
                ew_path = core.get("EW")
                em_path = core.get("EM_LOCK")
                ew_ok = False
                em_kind = None
                g_cands = None
                g_pref = None
                if ew_path and ew_path.exists():
                    try:
                        ew = ew_full if isinstance(ew_full, dict) else json.loads(ew_path.read_text(encoding="utf-8"))
                        ew_ok = (isinstance(ew, dict) and ew.get("derivation_status") == "DERIVED")
                        cs = ew.get("candidate_space") or {}
                        gb = cs.get("g_weak") if isinstance(cs, dict) else None
                        g_cands = (gb or {}).get("candidates") if isinstance(gb, dict) else None
                        g_pref = (gb or {}).get("preferred") if isinstance(gb, dict) else None
                    except Exception:
                        ew_ok = False
                        g_cands = None
                if em_path and em_path.exists():
                    try:
                        em = em_full if isinstance(em_full, dict) else json.loads(em_path.read_text(encoding="utf-8"))
                        if isinstance(em, dict):
                            em_kind = em.get("derivation_status")
                    except Exception:
                        em_kind = None

                if ew_ok and isinstance(g_cands, list) and len(g_cands) > 0:
                    dstat = "CANDIDATE-SET"
                    source = "EW_COUPLING_LOCK (derived from EM_LOCK alpha_RT candidates)"
                    artifact = str(ew_path.relative_to(REPO)).replace("\\", "/")
                    core_value = {
                        "candidates": [
                            {"id": c.get("id"), "expr": c.get("expr"), "value": c.get("approx")}
                            for c in g_cands if isinstance(c, dict)
                        ],
                        "preferred": g_pref,
                        "unit": "dimensionless",
                        "relation": "g = 4*sqrt(pi*alpha_RT) (since sin^2(theta_W)=1/4)",
                        "candidate_count": len(g_cands),
                    }
                    note = "Fallback: Core g_weak from EW lock candidate space; not promoted without alpha_RT DERIVED."
                else:
                    dstat = "HYP"
                    note = "sin²θ_W is derived, but g needs EM normalization (alpha_RT/Xi_RT) which is not fixed in Core yet."

        elif "Stark koppling" in name or name.strip() in {"g_s", "gs"}:
            canon_done = False
            # Prefer GS_CANON_DENOM_LOCK reduction if available (facit-free).
            if isinstance(gs_canon_full, dict) and str(gs_canon_full.get("derivation_status")) == "DERIVED":
                red = (gs_canon_full.get("reduced") or {}) if isinstance(gs_canon_full.get("reduced"), dict) else {}
                rg = red.get("g_s") if isinstance(red, dict) else None
                ra = red.get("alpha_s_RT") if isinstance(red, dict) else None
                if isinstance(rg, dict) and int(rg.get("kept") or 0) == 1 and isinstance(rg.get("candidates"), list) and len(rg.get("candidates")) == 1:
                    dstat = "DERIVED"
                    source = "GS_CANON_DENOM_LOCK"
                    artifact = str(core["GS_CANON"].relative_to(REPO)).replace("\\", "/")
                    pref_g = rg.get("preferred") if isinstance(rg.get("preferred"), dict) else (rg.get("candidates")[0] if rg.get("candidates") else None)
                    pref_a = ra.get("preferred") if isinstance(ra, dict) and isinstance(ra.get("preferred"), dict) else None
                    core_value = {
                        "type": "finite_candidate_set",
                        "quantity": "g_s",
                        "unit": "dimensionless",
                        "relation": "alpha_s_RT := g_s^2/(4*pi)",
                        "alpha_s_RT_preferred": pref_a,
                        "candidates": [{"id": c.get("id"), "expr": c.get("expr"), "value": c.get("approx")} for c in (rg.get("candidates") or []) if isinstance(c, dict)],
                        "preferred": pref_g,
                        "promotion_rule": "DERIVED iff C30-closure (alpha_s_RT=1/d requires d|K with K=30) reduces GS_LOCK to singleton",
                    }
                    note = "Core g_s promoted to DERIVED by GS_CANON_DENOM_LOCK (C30-closure d|K, K=30; facit-free)."
                    canon_done = True
                    # skip the legacy GS_LOCK block
                else:
                    pass


            if not canon_done:
                gs_path = core.get("GS")
                gs = gs_full if isinstance(gs_full, dict) else None
                if gs_path and gs_path.exists() and isinstance(gs, dict):
                    gs_kind = (gs or {}).get("derivation_status") if isinstance(gs, dict) else None
                    if gs_kind in {"CANDIDATE-SET", "DERIVED"}:
                        dstat = "CANDIDATE-SET" if gs_kind == "CANDIDATE-SET" else "DERIVED"
                        source = "GS_LOCK"
                        artifact = str(gs_path.relative_to(REPO)).replace("\\", "/")
                        cs = (gs.get("candidate_space") or {}) if isinstance(gs, dict) else {}
                        a = cs.get("alpha_s_RT") if isinstance(cs, dict) else None
                        g = cs.get("g_s") if isinstance(cs, dict) else None
                        a_c = a.get("candidates") if isinstance(a, dict) else None
                        g_c = g.get("candidates") if isinstance(g, dict) else None
                        a_pref = a.get("preferred") if isinstance(a, dict) else None
                        g_pref = g.get("preferred") if isinstance(g, dict) else None

                        # reduced view (optional)
                        red_a = None
                        red_g = None
                        if isinstance(cons_full, dict):
                            red_a = ((cons_full.get("reduced") or {}).get("alpha_s_RT"))
                            red_g = ((cons_full.get("reduced") or {}).get("g_s"))

                        core_value = {
                            "value": 1.0,
                            "gate": "PASS_STRUCT",
                            "relation": "alpha_s_RT := g_s^2/(4*pi)",
                            "unit": "dimensionless",
                            "alpha_s_RT": {
                                "candidate_count": len(a_c) if isinstance(a_c, list) else None,
                                "preferred": a_pref if isinstance(a_pref, dict) else None,
                                "candidates": [
                                    {"id": c.get("id"), "expr": c.get("expr")}
                                    for c in (a_c if isinstance(a_c, list) else [])
                                    if isinstance(c, dict)
                                ],
                                "candidates_top": _top(a_c, n=8, keep_keys=["id", "expr", "family", "complexity"])
                                if isinstance(a_c, list) else None,
                                "reduced": {"kept": red_a.get("kept"), "candidate_count": red_a.get("candidate_count"), "candidates": red_a.get("candidates"), "preferred": red_a.get("preferred")} if isinstance(red_a, dict) else None,
                            },
                            "g_s": {
                                "candidate_count": len(g_c) if isinstance(g_c, list) else None,
                                "preferred": g_pref if isinstance(g_pref, dict) else None,
                                "candidates": [
                                    {"id": c.get("id"), "expr": c.get("expr"), "value": c.get("approx")}
                                    for c in (g_c if isinstance(g_c, list) else [])
                                    if isinstance(c, dict)
                                ],
                                "candidates_top": _top(g_c, n=8, keep_keys=["id", "expr", "approx", "complexity", "source_alpha_s_id"])
                                if isinstance(g_c, list) else None,
                                "reduced": {"kept": red_g.get("kept"), "candidate_count": red_g.get("candidate_count"), "candidates": red_g.get("candidates"), "preferred": red_g.get("preferred")} if isinstance(red_g, dict) else None,
                            },
                        }
                        note = "Core exposes alpha_s_RT and g_s as finite candidate-sets (no facit selection). Preferred is min-complexity only."
                    else:
                        dstat = "HYP"
                        note = "GS_LOCK core artifact invalid; keep g_s as HYP."
                else:
                    dstat = "HYP"
                    note = "GS_LOCK core artifact missing; g_s not fixed in Core yet."
        else:
            dstat = "BLANK"

        entries.append({
            "parameter": name,
            "derivation_status": dstat,
            "validation_status": vstat,
            "source_lock": source,
            "artifact": artifact,
            "core_value": core_value,
            "core_scope": scope,
            "note": note,
        })

    out = {
        "version": "v0.11",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "policy": "NO-FACIT core index (no overlay refs read)",
        "entries": entries,
    }

    out_dir = REPO / "out" / "CORE_SM29_INDEX"
    out_dir.mkdir(parents=True, exist_ok=True)

    jpath = out_dir / "sm29_core_index_v0_11.json"
    jpath.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Markdown summary
    lines = [
        "# SM29 Core Index (v0.11)",
        "",
        "| Parameter | Derivation-status | Validation-status | Source | Artifact | Core value | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in entries:
        lines.append(
            f"| {e['parameter']} | {e['derivation_status']} | {e['validation_status']} | {e['source_lock'] or ''} | {e['artifact'] or ''} | {json.dumps(e.get('core_value'), ensure_ascii=False) if e.get('core_value') is not None else ''} | {e.get('note') or ''} |"
        )
    (out_dir / "sm29_core_index_v0_11.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"WROTE: {jpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
