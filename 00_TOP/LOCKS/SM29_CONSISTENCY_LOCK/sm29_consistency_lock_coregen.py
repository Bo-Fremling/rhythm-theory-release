#!/usr/bin/env python3
"""SM29_CONSISTENCY_LOCK coregen (NO-FACIT).

Goal
- Reduce several existing Core candidate-sets into *smaller* candidate-sets
  using only Core-internal rules.

Policy
- MUST NOT read Overlay/**
- MUST NOT read any *reference*.json
- MUST NOT score against PDG/CODATA/targets

Method
- v0.1: Deterministic "min complexity window": keep the first N_KEEP candidates
  in each lock's existing internal ordering.
- v0.2: Add a *Core-semantic* reducer for alpha_RT and the EW couplings derived
  from it.
- v0.8 (hardening): If EM_XI_INVARIANT_LOCK is present and DERIVED (duty=20/21),
  REQUIRE that alpha_RT be taken from the H-family (cap duty) among Z3-gated
  mode candidates, and require uniqueness (exactly one candidate at selected k).
  Also enforce the mode-gate 42 % k == 0 (k | 42).
- v0.9 (NEG evidence): When duty-lock is present, explicitly record evaluated NEG
  alternatives at the selected k (non-H families) as FAIL by the duty invariant.

Writes
- out/CORE_SM29_CONSISTENCY_LOCK/sm29_consistency_lock_core_v0_9.json
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[3]
LOCK = Path(__file__).resolve().parent.name

N_KEEP = 6

LSTAR = 1260
LCAP = 7
K_TICKS = 30


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _pick_latest(dir_rel: str, pattern: str) -> Optional[Path]:
    d = REPO / dir_rel
    cands = sorted(d.glob(pattern))
    return cands[-1] if cands else None


def _trim_candidates(cands: list, *, keep: int) -> list:
    out = []
    for c in cands[: max(0, int(keep))]:
        if isinstance(c, dict):
            out.append({k: c.get(k) for k in ["id", "expr", "approx", "family", "complexity", "parents", "artifact", "ratios_pred", "policy_complexity", "source_xi_expr", "source_alpha_id", "source_alpha_s_id", "source_alpha_s_expr"] if k in c})
        else:
            out.append(c)
    return out


def _reduce_block(name: str, *, candidates: list, preferred: Optional[dict]) -> dict:
    kept = min(len(candidates), N_KEEP)
    out = {
        "name": name,
        "candidate_count": len(candidates),
        "kept": kept,
        "preferred": preferred,
        "candidates": _trim_candidates(candidates, keep=kept),
    }
    return out


def _parse_k_from_xi_expr(xi_expr: str) -> tuple[Optional[int], Optional[str]]:
    """Parse (k, family_tag) from supported Xi expressions.

    Supported:
      B: 2*pi*k/1260
      E: 2*pi*(k*K - 2)/(K*1260)   (AB-edge corrected; K=30)
      F: 2*pi*(k*K-(2+2/10-1/(10*(42-k))))/(K*1260)  (AB-edge + rho/mode corr)
      G: 2*pi*(k*K-(2+2/10-1/(10*(42-k))-1/(10*(42-k)*K*L_cap))))/(K*1260) (adds cap-arming corr)
      H: same as G but with duty factor 20/21 on the cap term
    """
    s = (xi_expr or "").replace(" ", "")

    # B family
    if s.startswith("2*pi*"):
        tail = s[len("2*pi*") :]
        if f"/{LSTAR}" in tail and "(" not in tail and ")" not in tail:
            k_str, den = tail.split("/", 1)
            if den == str(LSTAR):
                try:
                    return int(k_str), "B"
                except Exception:
                    return None, None

    # E family: 2*pi*(k*K-2)/(K*LSTAR)
    m = re.match(r"^2\*pi\*\((\d+)\*(\d+)-2\)/\((\d+)\*(\d+)\)$", s)
    if m:
        k, K1, K2, L = m.groups()
        try:
            k = int(k)
            K1 = int(K1)
            K2 = int(K2)
            L = int(L)
        except Exception:
            return None, None
        if K1 == K_TICKS and K2 == K_TICKS and L == LSTAR:
            return k, "E"

    # F family: 2*pi*(k*K-(2+2/10-1/(10*(42-k))))/(K*LSTAR)
    if s.startswith("2*pi*(") and s.endswith(f")/({K_TICKS}*{LSTAR})") and (f"*{K_TICKS}-" in s):
        try:
            # parse leading k
            head = s[len("2*pi*(") :]
            k_str, rest = head.split(f"*{K_TICKS}-", 1)
            k = int(k_str)
            # require the rho/mode-correction structure and the explicit (42-k) occurrence
            if f"(42-{k})" in s and "2+2/10-1/(10*" in s:
                # H family uses a duty-weighted cap term (20/21)
                if "20/(21*10*(42-" in s and f"*{K_TICKS}*{LCAP}" in s:
                    return k, "H"
                # G family adds a raw cap-arming correction term
                if f"*{K_TICKS}*{LCAP}" in s and "-1/(10*(42-" in s:
                    return k, "G"
                return k, "F"
        except Exception:
            pass

    return None, None


def _reduce_alpha_z3_phase(
    alpha_cands: list[dict],
    *,
    keep: int,
    require_family_h: bool,
    duty_expr: Optional[str],
) -> tuple[list[dict], Optional[dict], dict]:
    """Reduce alpha_RT using a Core-semantic Z3+phase rule.

    Returns (reduced_candidates, preferred, meta).
    """
    # Candidates come from EM_LOCK alpha_RT, each carries source_xi_expr.
    z3 = []
    for c in alpha_cands:
        if not isinstance(c, dict):
            continue
        k, fam = _parse_k_from_xi_expr(str(c.get("source_xi_expr") or ""))
        if k is None:
            continue
        if k % 3 != 0:
            continue
        z3.append((k, fam or "?", c))

    meta = {
        "method": "z3_phase_min_k",
        "rule": {
            "prefer_family": (
                f"Prefer H if present (cap duty {duty_expr or '20/21'}), else G (cap-arming), else F (rho/mode), else E (AB-edge), else B (2*pi*k/{LSTAR})."
            ),
            "z3_gate": "k % 3 == 0",
            "mode_gate": "42 % k == 0 (k | 42)",
            "tie_break": "fundamental harmonic (min k)",
            "require_family_h_if_duty_lock": bool(require_family_h),
        },
    }

    if not z3:
        meta["fatal"] = "no z3-phase candidates found"
        return [], None, meta

    # Prefer family H when available. If the duty invariant is DERIVED, require H.
    z3_h = [t for t in z3 if t[1] == "H"]
    z3_g = [t for t in z3 if t[1] == "G"]
    z3_f = [t for t in z3 if t[1] == "F"]
    z3_e = [t for t in z3 if t[1] == "E"]
    z3_b = [t for t in z3 if t[1] == "B"]

    if require_family_h and not z3_h:
        meta["fatal"] = "duty_lock_present_but_no_H_family_candidates"
        return [], None, meta

    pool = z3_h if z3_h else (z3_g if z3_g else (z3_f if z3_f else (z3_e if z3_e else (z3_b if z3_b else z3))))

    # Mode-gate: k must divide 42 (enforces the global-frame mode closure).
    pool = [t for t in pool if (t[0] > 0 and (42 % int(t[0]) == 0))]
    if not pool:
        meta["fatal"] = "no_candidates_left_after_mode_gate"
        return [], None, meta

    pool.sort(key=lambda t: t[0])
    k0 = int(pool[0][0])
    picked_all = [c for k, fam, c in pool if int(k) == k0]
    if len(picked_all) != 1:
        meta["fatal"] = "selected_k_not_unique"
        meta["selected_k"] = k0
        meta["selected_k_count"] = len(picked_all)
        return [], None, meta

    # NEG evidence: if duty lock is present (require_family_h), record alternative families
    # at the selected k that would otherwise survive Z3+mode gates but are excluded by the
    # duty invariant (requires H family cap coefficient 20/21).
    neg_same_k = []
    if require_family_h:
        picked_family = str(pool[0][1]) if pool else None
        # z3 contains tuples (k, fam, cand) already Z3-gated.
        for kk, ff, cc in z3:
            if int(kk) != int(k0):
                continue
            if int(kk) <= 0 or (42 % int(kk) != 0):
                continue
            if str(ff) == str(picked_family):
                continue
            if not isinstance(cc, dict):
                continue
            neg_same_k.append({
                'k': int(kk),
                'family': str(ff),
                'alpha_id': str(cc.get('id')) if cc.get('id') is not None else None,
                'xi_expr': str(cc.get('source_xi_expr') or ''),
                'expect': 'FAIL (duty invariant requires H family: cap coeff 20/21)',
            })
        # sort deterministically
        neg_same_k.sort(key=lambda d: (d.get('family') or '', d.get('alpha_id') or '', d.get('xi_expr') or ''))
        meta['neg_alternatives_same_k'] = neg_same_k

    picked = picked_all[: max(1, int(keep))]
    pref = None
    if picked:
        p = picked[0]
        pref = {k: p.get(k) for k in ["id", "expr", "approx"] if k in p}
        pref["rule"] = "z3_phase_fundamental_k (unique)"
    meta["selected_k"] = k0
    return picked, pref, meta




def _reduce_lepton_mass_by_arming(lep_cands: list[dict], *, require_arming: bool = True) -> tuple[list[dict], Optional[dict], dict]:
    """Reduce lepton mass ratio candidates using Core semantics.

    Rule (v0.3): If cap is present (L_cap != 0), require the explicit arming/disarming
    postulate P_ARM to be applied in the candidate construction.

    Implementation: keep only candidates with policy_complexity.uses_arming_rule == True.
    Tie-break: retain existing ordering and pick first.
    """
    meta = {
        "method": "require_arming_when_cap",
        "rule": {
            "require_arming": bool(require_arming),
            "when": f"L_cap={LCAP} (nonzero)",
            "predicate": "policy_complexity.uses_arming_rule == True",
            "tie_break": "first in existing order",
        },
    }
    if not require_arming:
        meta["note"] = "arming not required; no reduction performed"
        return [], None, meta

    kept = []
    for c in lep_cands:
        if not isinstance(c, dict):
            continue
        pc = c.get("policy_complexity") or {}
        if (pc.get("uses_arming_rule") is True):
            kept.append(c)

    if not kept:
        meta["fallback"] = "no candidates satisfied arming rule; using min_complexity_window"
        return [], None, meta

    # Keep only the minimal fields (core-only)
    trimmed = [
        {k: c.get(k) for k in ["id", "artifact", "ratios_pred", "policy_complexity"] if k in c}
        for c in kept
    ]

    pref = None
    if trimmed:
        pref = {k: trimmed[0].get(k) for k in ["id", "artifact", "ratios_pred", "policy_complexity"] if k in trimmed[0]}
        pref["rule"] = "require_arming_when_cap (first kept)"

    meta["kept_count"] = len(trimmed)
    return trimmed, pref, meta


def _reduce_nu_patterns(patterns: list[dict]) -> tuple[list[dict], Optional[dict], dict]:
    """Reduce neutrino mass-pattern candidates using Core semantics only.

    Rule (v0.4): if any pattern is already marked pattern_status == 'DERIVED',
    keep only those DERIVED patterns (in existing order). Otherwise keep the first
    N_KEEP patterns.

    This is facit-free: relies only on the NU_MECHANISM_LOCK internal status label.
    """
    meta = {
        "method": "keep_derived_patterns",
        "rule": {
            "predicate": "pattern_status == 'DERIVED'",
            "fallback": f"min_complexity_window (first N={N_KEEP})",
            "tie_break": "existing order",
        },
    }
    derived = [p for p in patterns if isinstance(p, dict) and p.get("pattern_status") == "DERIVED"]
    if derived:
        kept = derived
        meta["kept_kind"] = "derived_only"
    else:
        kept = [p for p in patterns[:N_KEEP] if isinstance(p, dict)]
        meta["kept_kind"] = "window"

    pref = None
    if kept:
        p0 = kept[0]
        pref = {k: p0.get(k) for k in ["id", "n", "m_over_m_e", "delta_m2_ratio_exact", "note", "pattern_status"]}
        pref["rule"] = "keep_derived_patterns (first kept)"
    meta["kept_count"] = len(kept)
    return kept, pref, meta

def main() -> int:
    # Inputs (latest artifacts)
    em_p = _pick_latest("out/CORE_EM_LOCK", "em_lock_core_v*.json")
    em_xi_p = _pick_latest("out/CORE_EM_XI_INVARIANT_LOCK", "em_xi_invariant_lock_core_v*.json")
    ew_p = _pick_latest("out/CORE_EW_COUPLING_LOCK", "ew_coupling_core_v*.json")
    gs_p = _pick_latest("out/CORE_GS_LOCK", "gs_lock_core_v*.json")
    higgs_p = _pick_latest("out/CORE_HIGGS_VEV_LOCK", "higgs_vev_lock_core_v*.json")
    lep_p = _pick_latest("out/CORE_LEPTON_MASS_LOCK", "lepton_mass_lock_core_candidates_v*.json")
    nu_p = _pick_latest("out/CORE_NU_MECHANISM_LOCK", "nu_mechanism_lock_v*.json")

    blocks: dict[str, dict] = {}
    inputs: dict[str, str] = {}

    selected_alpha_ids: set[str] = set()
    alpha_reduce_meta: Optional[dict] = None

    # If the duty invariant is DERIVED (20/21), we require H-family for alpha_RT.
    require_family_h = False
    duty_expr: Optional[str] = None
    alpha_reduce_fatal: Optional[str] = None

    if em_xi_p and em_xi_p.exists():
        emxi = _load_json(em_xi_p)
        inputs["EM_XI_INVARIANT_LOCK"] = str(em_xi_p.relative_to(REPO)).replace("\\", "/")
        duty = (emxi.get("duty_factor") or {}) if isinstance(emxi, dict) else {}
        duty_expr = str(duty.get("expr") or "")
        if (emxi.get("derivation_status") == "DERIVED") and (duty_expr == "20/21"):
            require_family_h = True

    if em_p and em_p.exists():
        em = _load_json(em_p)
        inputs["EM_LOCK"] = str(em_p.relative_to(REPO)).replace("\\", "/")
        cs = (em.get("candidate_space") or {}) if isinstance(em, dict) else {}
        a = cs.get("alpha_RT") if isinstance(cs, dict) else None
        if isinstance(a, dict):
            cands = a.get("candidates") or []
            cands_list = list(cands) if isinstance(cands, list) else []

            # v0.8 reducer: Z3-phase fundamental-k selection.
            # If duty invariant is DERIVED (20/21), require H-family (cap duty).
            picked, pref2, meta = _reduce_alpha_z3_phase(
                [c for c in cands_list if isinstance(c, dict)],
                keep=1,
                require_family_h=require_family_h,
                duty_expr=duty_expr,
            )
            alpha_reduce_meta = meta
            alpha_reduce_fatal = meta.get("fatal") if isinstance(meta, dict) else None
            if picked:
                selected_alpha_ids = {str(c.get("id")) for c in picked if isinstance(c, dict) and c.get("id")}
                blocks["alpha_RT"] = {
                    "name": "alpha_RT",
                    "candidate_count": len(cands_list),
                    "kept": len(picked),
                    "preferred": pref2,
                    "candidates": _trim_candidates(picked, keep=len(picked)),
                    "meta": meta,
                }
            else:
                pref = (a.get("preferred") if isinstance(a.get("preferred"), dict) else (em.get("tie_break") or {}).get("preferred", {}).get("alpha_RT"))
                blocks["alpha_RT"] = _reduce_block("alpha_RT", candidates=cands_list, preferred=pref if isinstance(pref, dict) else None)
                blocks["alpha_RT"]["meta"] = meta

    if ew_p and ew_p.exists():
        ew = _load_json(ew_p)
        inputs["EW_COUPLING_LOCK"] = str(ew_p.relative_to(REPO)).replace("\\", "/")
        cs = (ew.get("candidate_space") or {}) if isinstance(ew, dict) else {}
        # Reduce g_weak consistently with alpha_RT reduction if we selected a unique alpha id.
        for key in ["g_weak", "g_hyper", "g_prime", "e_charge"]:
            blk = cs.get(key) if isinstance(cs, dict) else None
            if not (isinstance(blk, dict) and isinstance(blk.get("candidates"), list)):
                continue
            cands = list(blk.get("candidates"))
            pref = blk.get("preferred") if isinstance(blk.get("preferred"), dict) else None
            if key in {"g_weak", "g_hyper"} and selected_alpha_ids:
                filtered = []
                for c in cands:
                    if not isinstance(c, dict):
                        continue
                    sid = c.get("source_alpha_id")
                    if sid is None:
                        continue
                    if str(sid) in selected_alpha_ids:
                        filtered.append(c)
                if filtered:
                    blocks[key] = {
                        "name": key,
                        "candidate_count": len(cands),
                        "kept": len(filtered),
                        "preferred": {k: filtered[0].get(k) for k in ["id", "expr", "approx"] if k in filtered[0]},
                        "candidates": _trim_candidates(filtered, keep=len(filtered)),
                        "meta": {
                            "method": "inherits_alpha_reduction",
                            "alpha_reduction": alpha_reduce_meta,
                        },
                    }
                    continue
            blocks[key] = _reduce_block(key, candidates=cands, preferred=pref)

    if gs_p and gs_p.exists():
        gs = _load_json(gs_p)
        inputs["GS_LOCK"] = str(gs_p.relative_to(REPO)).replace("\\", "/")
        cs = (gs.get("candidate_space") or {}) if isinstance(gs, dict) else {}
        for key in ["alpha_s_RT", "g_s"]:
            blk = cs.get(key) if isinstance(cs, dict) else None
            if isinstance(blk, dict) and isinstance(blk.get("candidates"), list):
                blocks[key] = _reduce_block(key, candidates=list(blk.get("candidates")), preferred=blk.get("preferred") if isinstance(blk.get("preferred"), dict) else None)

    if higgs_p and higgs_p.exists():
        hg = _load_json(higgs_p)
        inputs["HIGGS_VEV_LOCK"] = str(higgs_p.relative_to(REPO)).replace("\\", "/")
        cs = (hg.get("candidate_space") or {}) if isinstance(hg, dict) else {}
        for key in ["v_hat", "lambda_H", "mH_hat"]:
            blk = cs.get(key) if isinstance(cs, dict) else None
            if isinstance(blk, dict) and isinstance(blk.get("candidates"), list):
                blocks[key] = _reduce_block(key, candidates=list(blk.get("candidates")), preferred=blk.get("preferred") if isinstance(blk.get("preferred"), dict) else None)

    if lep_p and lep_p.exists():
        lep = _load_json(lep_p)
        inputs["LEPTON_MASS_LOCK"] = str(lep_p.relative_to(REPO)).replace("\\", "/")
        if isinstance(lep, dict) and isinstance(lep.get("candidates"), list):
            cands = list(lep.get("candidates"))
            pref = (lep.get("tie_break") or {}).get("preferred")

            picked, pref2, meta = _reduce_lepton_mass_by_arming([c for c in cands if isinstance(c, dict)], require_arming=(LCAP != 0))
            if picked:
                blocks["lepton_mass_ratios"] = {
                    "name": "lepton_mass_ratios",
                    "candidate_count": len(cands),
                    "kept": len(picked),
                    "preferred": pref2,
                    "candidates": picked,
                    "meta": meta,
                }
            else:
                blocks["lepton_mass_ratios"] = {
                    "name": "lepton_mass_ratios",
                    "candidate_count": len(cands),
                    "kept": len(cands),
                    "preferred": pref if isinstance(pref, dict) else None,
                    "candidates": [
                        {k: c.get(k) for k in ["id", "artifact", "ratios_pred", "policy_complexity"] if k in c}
                        for c in cands if isinstance(c, dict)
                    ],
                    "meta": meta,
                }
    if nu_p and nu_p.exists():
        nu = _load_json(nu_p)
        inputs["NU_MECHANISM_LOCK"] = str(nu_p.relative_to(REPO)).replace("\\", "/")
        res = nu.get("results") if isinstance(nu, dict) else None
        patterns = (res or {}).get("patterns") if isinstance(res, dict) else None
        sel = (res or {}).get("selection") if isinstance(res, dict) else None
        pref_id = sel.get("preferred_pattern_id") if isinstance(sel, dict) else None
        pref = None
        if isinstance(patterns, list) and pref_id is not None:
            for p in patterns:
                if isinstance(p, dict) and p.get("id") == pref_id:
                    pref = {k: p.get(k) for k in ["id", "n", "m_over_m_e", "delta_m2_ratio_exact", "note", "pattern_status"]}
                    break
        p_list = [p for p in (patterns if isinstance(patterns, list) else []) if isinstance(p, dict)]
        kept, pref2, meta = _reduce_nu_patterns(p_list)
        blocks["nu_patterns"] = {
            "name": "nu_patterns",
            "candidate_count": len(p_list),
            "kept": len(kept),
            "preferred": pref2 if pref2 is not None else pref,
            "patterns": [
                {k: p.get(k) for k in ["id", "n", "m_over_m_e", "delta_m2_ratio_exact", "note", "pattern_status"]}
                for p in kept
                if isinstance(p, dict)
            ],
            "meta": meta,
        }

    fatal = []
    if alpha_reduce_fatal:
        fatal.append({"block": "alpha_RT", "fatal": alpha_reduce_fatal, "meta": alpha_reduce_meta})

    out = {
        "version": "v0.9",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "lock": LOCK,
        "derivation_status": "DERIVED",
        "validation_status": "UNTESTED",
        "policy": {
            "no_facit": True,
            "method": "mixed (alpha: z3_phase_fundamental_k with optional duty->H requirement; lepton: require_arming_when_cap; others: min_complexity_window)",
            "N_KEEP": N_KEEP,
            "note": "Reduced sets are derived deterministically from existing Core candidate ordering. No overlay feedback.",
        },
        "inputs": inputs,
        "reduced": blocks,
        "fatal": fatal,
    }

    out_dir = REPO / "out" / f"CORE_{LOCK}"
    out_dir.mkdir(parents=True, exist_ok=True)
    if fatal:
        jp_fail = out_dir / "sm29_consistency_lock_core_v0_9_FAIL.json"
        jp_fail.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"WROTE: {jp_fail}")
        return 10

    jp = out_dir / "sm29_consistency_lock_core_v0_9.json"
    jp.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    mp = out_dir / "sm29_consistency_lock_core_v0_9.md"
    mp.write_text(
        "\n".join(
            [
                "# SM29_CONSISTENCY_LOCK Core (v0.8)",
                "",
                "- Derivation-status: **DERIVED** (reduced views only)",
                "- Validation-status: **UNTESTED**",
                "",
                f"- Method: alpha_RT uses Z3-phase fundamental-k (and requires H-family if duty=20/21 is DERIVED); other blocks keep first N={N_KEEP} in their internal ordering.",
                "",
                "## Reduced blocks",
            ]
            + [f"- {k}: kept {v.get('kept')}/{v.get('candidate_count')}" for k, v in sorted(blocks.items())]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"WROTE: {jp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
