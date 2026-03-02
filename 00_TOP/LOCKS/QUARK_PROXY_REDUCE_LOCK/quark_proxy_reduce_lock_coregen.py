#!/usr/bin/env python3
"""QUARK_PROXY_REDUCE_LOCK coregen (NO-FACIT).

Purpose
- Turn QUARK_PROXY_LOCK's finite candidate-spaces into *singleton* candidate-spaces
  using only the already-derived, facit-free preferred-rule embedded in the Core
  artifact.

Why this exists
- QUARK_PROXY_LOCK correctly keeps a *candidate-space* so Compare can report
  any-hit vs preferred-hit without influencing Core.
- Once the preferred selection is itself derived purely from Core metadata
  (choice.q, scan.q_vals, scan.eps_nc), we can promote the quark-ratio proxies
  from CANDIDATE-SET -> DERIVED by reducing to the preferred element.

Rules
- MUST NOT read 00_TOP/OVERLAY/**, *reference*.json, PDG/CODATA/targets.
- Reads only out/CORE_QUARK_PROXY_LOCK/quark_proxy_core_v*.json
- Writes only to out/CORE_QUARK_PROXY_REDUCE_LOCK/

Hardening (v0.3)
- Recompute preferred by matching the expected (p,d) from preferred_rule
  against the upstream candidate list.
- HARD FAIL if match-count != 1 (no match OR duplicated match).
- HARD FAIL if upstream block.preferred is missing OR does not exactly match
  the recomputed preferred candidate.
- Determinism self-test: order-independence under candidate list reversal.

This removes the last "soft" fallback (keep first candidate) and makes the
singleton reduction structurally dependent on the upstream Core invariants.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[3]


def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _pick_latest(out_dir: Path, pattern: str) -> Optional[Path]:
    cands = sorted(out_dir.glob(pattern))
    return cands[-1] if cands else None


def _as_int(x) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None


def _exact_subset(d: dict, keys: list[str]) -> dict:
    return {k: d.get(k) for k in keys}


def _recompute_preferred(block: dict, *, exp_pd: tuple[int, int]) -> tuple[Optional[dict], dict]:
    """Return (preferred_candidate, meta).

    Recompute preferred by filtering candidates on expected (p,d).
    This makes the reduction independent of candidate ordering.
    """
    base = str(block.get("base") or "")
    cands = block.get("candidates")
    if not isinstance(cands, list):
        return None, {"base": base, "issue": "BAD_CANDIDATES_LIST"}

    p_exp, d_exp = exp_pd
    matches = []
    for c in cands:
        if not isinstance(c, dict):
            continue
        p_i = _as_int(c.get("p"))
        d_i = _as_int(c.get("d"))
        if p_i == p_exp and d_i == d_exp:
            matches.append(c)

    meta = {
        "base": base,
        "expected_pd": [p_exp, d_exp],
        "match_count": len(matches),
    }

    if len(matches) != 1:
        meta["issue"] = "EXPECTED_PD_MATCH_NOT_UNIQUE"
        return None, meta

    # Determinism self-test: reversing the list must not change which candidate matches.
    rev = list(reversed(cands))
    matches_rev = [
        c for c in rev
        if isinstance(c, dict) and _as_int(c.get("p")) == p_exp and _as_int(c.get("d")) == d_exp
    ]
    meta["order_independent_reverse"] = (len(matches_rev) == 1 and matches_rev[0] == matches[0])

    return matches[0], meta


def _reduce_block(block: dict, *, exp_pd: tuple[int, int]) -> tuple[dict, list[dict]]:
    """Keep only the recomputed preferred candidate.

    Returns (reduced_block, issues_for_this_block).
    """
    if not isinstance(block, dict):
        return block, [{"issue": "BLOCK_NOT_DICT"}]

    upstream_pref = block.get("preferred")
    recomputed, meta = _recompute_preferred(block, exp_pd=exp_pd)

    issues: list[dict] = []
    if recomputed is None:
        issues.append({"issue": meta.get("issue", "RECOMPUTE_FAILED"), **meta})

    if not isinstance(upstream_pref, dict):
        issues.append({"issue": "MISSING_UPSTREAM_PREFERRED", "base": block.get("base")})

    # Exact match check: upstream preferred must equal the recomputed candidate.
    if isinstance(upstream_pref, dict) and isinstance(recomputed, dict):
        a = _exact_subset(upstream_pref, ["id", "expr", "p", "d", "approx"])
        b = _exact_subset(recomputed,     ["id", "expr", "p", "d", "approx"])
        if a != b:
            issues.append({
                "issue": "UPSTREAM_PREFERRED_MISMATCH",
                "base": block.get("base"),
                "upstream": a,
                "recomputed": b,
            })

    kept = [recomputed] if isinstance(recomputed, dict) and not issues else []

    out = {
        "type": "reduced_candidate_set",
        "base": block.get("base"),
        "preferred": recomputed if isinstance(recomputed, dict) and not issues else None,
        "candidates": kept,
        "meta": {
            "kept_count": len(kept),
            "expected_pd": list(exp_pd),
            "rule": "match_expected_pd_and_confirm_upstream_preferred (hard)",
            "self_test": {
                "order_independent_reverse": bool(meta.get("order_independent_reverse")) if isinstance(meta, dict) else False,
            },
        },
    }
    return out, issues


def _expect_pd(preferred_rule: dict, *, base: str) -> tuple[int, int] | None:
    """Map ratio base -> expected (p,d) from QUARK_PROXY_LOCK.preferred_rule."""
    pr = preferred_rule or {}
    g12 = (pr.get("gap12") or {})
    g23 = (pr.get("gap23") or {})

    if base == "u.r12":
        u = (g12.get("u") or {})
        return int(u.get("p", 0)), int(u.get("d", 0))
    if base == "u.r23":
        u = (g23.get("u") or {})
        return int(u.get("p", 0)), int(u.get("d", 0))
    if base == "d.r12":
        d = (g12.get("d") or {})
        return int(d.get("p", 0)), int(d.get("d", 0))
    if base == "d.r23":
        d = (g23.get("d") or {})
        return int(d.get("p", 0)), int(d.get("d", 0))

    return None


def _validate_reduction(reduced: dict, *, preferred_rule: dict) -> list[dict]:
    """Return a list of validation issues (empty => PASS)."""
    issues: list[dict] = []

    rcs = (reduced.get("reduced_candidate_space") or {})
    for key in ("m_u_over_m_c", "m_c_over_m_t", "m_d_over_m_s", "m_s_over_m_b"):
        blk = rcs.get(key) or {}
        base = str(blk.get("base") or "")
        pref = blk.get("preferred")
        exp = _expect_pd(preferred_rule, base=base)

        if not isinstance(pref, dict):
            issues.append({
                "ratio": key,
                "base": base,
                "issue": "MISSING_PREFERRED",
                "expect": exp,
            })
            continue

        p = pref.get("p")
        d = pref.get("d")
        if exp is None:
            issues.append({
                "ratio": key,
                "base": base,
                "issue": "UNKNOWN_BASE",
                "preferred_pd": [p, d],
            })
            continue

        try:
            p_i = int(p)
            d_i = int(d)
        except Exception:
            issues.append({
                "ratio": key,
                "base": base,
                "issue": "BAD_PREFERRED_PD",
                "preferred_pd": [p, d],
                "expect": list(exp),
            })
            continue

        if (p_i, d_i) != exp:
            issues.append({
                "ratio": key,
                "base": base,
                "issue": "PREFERRED_PD_MISMATCH",
                "preferred_pd": [p_i, d_i],
                "expect": list(exp),
            })

    return issues


def main() -> int:
    out_dir = REPO / "out" / "CORE_QUARK_PROXY_REDUCE_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    src_dir = REPO / "out" / "CORE_QUARK_PROXY_LOCK"
    src = _pick_latest(src_dir, "quark_proxy_core_v*.json")
    if not src or not src.exists():
        raise SystemExit("Missing Core QUARK_PROXY_LOCK artifact: out/CORE_QUARK_PROXY_LOCK/quark_proxy_core_v*.json")

    obj = _read_json(src)
    cs = obj.get("candidate_space") or {}

    preferred_rule = obj.get("preferred_rule") or {}

    # Precompute expected (p,d) per ratio (from upstream preferred_rule).
    exp_map = {}
    for key, base in {
        "m_u_over_m_c": "u.r12",
        "m_c_over_m_t": "u.r23",
        "m_d_over_m_s": "d.r12",
        "m_s_over_m_b": "d.r23",
    }.items():
        exp = _expect_pd(preferred_rule, base=base)
        if exp is not None:
            exp_map[key] = exp

    # Reduce each block and collect per-block issues (hard-fail if any).
    reduced_space = {}
    per_block_issues: list[dict] = []
    for key in ("m_u_over_m_c", "m_c_over_m_t", "m_d_over_m_s", "m_s_over_m_b"):
        blk = cs.get(key) or {}
        exp_pd = exp_map.get(key, (0, 0))
        rblk, issues_blk = _reduce_block(blk, exp_pd=exp_pd)
        reduced_space[key] = rblk
        for it in issues_blk:
            per_block_issues.append({"ratio": key, **it})

    reduced = {
        "version": "v0.3",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "inputs": {"quark_proxy": str(src.relative_to(REPO)).replace("\\", "/")},
        "preferred_rule": preferred_rule,
        "semantic_gate": obj.get("semantic_gate"),
        "reduced_candidate_space": {
            **reduced_space,
            "note": "Singleton reduction of QUARK_PROXY_LOCK candidate-space using facit-free preferred_rule already derived from FLAVOR_LOCK metadata.",
        },
    }

    issues = []
    issues.extend(per_block_issues)
    issues.extend(_validate_reduction(reduced, preferred_rule=preferred_rule))
    reduced["validation"] = {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "rule": "Recompute expected (p,d) from preferred_rule; require unique match in candidates AND exact equality with upstream preferred; plus base->(p,d) mapping check.",
    }

    if issues:
        # HARD FAIL (no silent fallback) — keeps Core honest.
        out_dir.mkdir(parents=True, exist_ok=True)
        jp_fail = out_dir / "quark_proxy_reduce_core_v0_3_FAIL.json"
        jp_fail.write_text(json.dumps(reduced, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"WROTE: {jp_fail}")
        return 10

    p = out_dir / "quark_proxy_reduce_core_v0_3.json"
    p.write_text(json.dumps(reduced, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
