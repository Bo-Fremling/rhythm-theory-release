#!/usr/bin/env python3
"""QUARK_PROXY_NEG_LOCK coregen (NO-FACIT).

Purpose
- Add explicit *negative controls* around QUARK_PROXY_LOCK preferred-rule.
- This does NOT change quark proxy values; it validates that the preferred-rule
  is non-degenerate and that nearby rule-variants would change the preferred (when
  ladders have >1 element).

Inputs (Core only)
- out/CORE_QUARK_PROXY_LOCK/quark_proxy_core_v*.json
- out/CORE_FLAVOR_LOCK/flavor_ud_core_v*.json (for scan ladders + eps signs)

Hard gates (FAIL => exit 10)
- Canonical preferred (p,d) must exist in the candidate list for each ratio.
- For each NEG variant where it is *meaningful* (ladder has >=2), the NEG-picked
  denominator MUST differ from canonical, and the corresponding (p,d) MUST also
  exist as a candidate. This ensures the preferred-rule is doing real work and
  is testable by contrast.

Writes
- out/CORE_QUARK_PROXY_NEG_LOCK/quark_proxy_neg_core_v0_1.json
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


def _pick_latest(out_dir: Path, pattern: str) -> Optional[Path]:
    cands = sorted(out_dir.glob(pattern))
    return cands[-1] if cands else None


def _extreme(vals: list[int], kind: str) -> Optional[int]:
    if not vals:
        return None
    if kind == "min":
        return min(int(x) for x in vals)
    if kind == "max":
        return max(int(x) for x in vals)
    raise ValueError(kind)


def _has_pd(cands: list[dict], p: int, d: int) -> bool:
    for c in cands:
        if not isinstance(c, dict):
            continue
        if int(c.get("p")) == int(p) and int(c.get("d")) == int(d):
            return True
    return False


def main() -> int:
    out_dir = REPO / "out" / f"CORE_{LOCK}"
    out_dir.mkdir(parents=True, exist_ok=True)

    qp_dir = REPO / "out" / "CORE_QUARK_PROXY_LOCK"
    qp = _pick_latest(qp_dir, "quark_proxy_core_v*.json")
    if not qp or not qp.exists():
        raise SystemExit("Missing Core QUARK_PROXY_LOCK artifact")

    fl_dir = REPO / "out" / "CORE_FLAVOR_LOCK"
    fl = _pick_latest(fl_dir, "flavor_ud_core_v*.json")
    if not fl or not fl.exists():
        raise SystemExit("Missing Core FLAVOR_LOCK artifact")

    qpj = _read_json(qp)
    flj = _read_json(fl)

    cs = (qpj.get("candidate_space") or {})
    pr = (qpj.get("preferred_rule") or {})

    scan = (flj.get("scan") or {})
    su = scan.get("u") or {}
    sd = scan.get("d") or {}

    u_q_vals = [int(x) for x in (su.get("q_vals") or []) if isinstance(x, (int, float))]
    d_q_vals = [int(x) for x in (sd.get("q_vals") or []) if isinstance(x, (int, float))]
    u_eps = float(su.get("eps_nc", 0.0))
    d_eps = float(sd.get("eps_nc", 0.0))

    issues: list[dict] = []

    def _canonical_pd(key: str) -> tuple[int, int] | None:
        blk = cs.get(key)
        if not isinstance(blk, dict):
            return None
        pref = blk.get("preferred")
        if not isinstance(pref, dict):
            return None
        try:
            return int(pref.get("p")), int(pref.get("d"))
        except Exception:
            return None

    # Canonical must exist in candidate list
    canonical = {}
    for key in ("m_u_over_m_c", "m_c_over_m_t", "m_d_over_m_s", "m_s_over_m_b"):
        blk = cs.get(key)
        if not isinstance(blk, dict):
            issues.append({"type": "missing_block", "key": key})
            continue
        cands = blk.get("candidates")
        if not isinstance(cands, list) or not cands:
            issues.append({"type": "missing_candidates", "key": key})
            continue
        pd = _canonical_pd(key)
        if pd is None:
            issues.append({"type": "missing_preferred_pd", "key": key})
            continue
        p0, d0 = pd
        if not _has_pd(cands, p0, d0):
            issues.append({"type": "canonical_pd_not_in_candidates", "key": key, "p": p0, "d": d0})
        canonical[key] = {"p": p0, "d": d0}

    # NEG variants
    neg = []

    # gap12 NEG: use min ladder denom instead of max (when meaningful)
    # For u12 -> affects m_u_over_m_c, for d12 -> affects m_d_over_m_s
    for sec, qvals, key, p_from in (
        ("u", u_q_vals, "m_u_over_m_c", "choice.q"),
        ("d", d_q_vals, "m_d_over_m_s", "choice.q"),
    ):
        if len(qvals) >= 2 and key in canonical:
            d_can = int(canonical[key]["d"])
            d_alt = int(_extreme(qvals, "min") or d_can)
            p_can = int(canonical[key]["p"])
            if d_alt == d_can:
                issues.append({"type": "neg_gap12_degenerate", "sector": sec, "key": key, "canon_d": d_can, "alt_d": d_alt, "q_vals": qvals})
            else:
                # alt must be present as a candidate
                blk = cs.get(key) or {}
                cands = blk.get("candidates") or []
                ok = _has_pd(cands, p_can, d_alt)
                if not ok:
                    issues.append({"type": "neg_gap12_pd_missing", "sector": sec, "key": key, "p": p_can, "d_alt": d_alt})
                neg.append({
                    "name": f"NEG_gap12_min_denom_{sec}",
                    "key": key,
                    "canon": {"p": p_can, "d": d_can},
                    "alt": {"p": p_can, "d": d_alt},
                    "q_vals": qvals,
                    "expect": "DIFF (non-degenerate)" if d_alt != d_can else "DEGENERATE",
                })

    # gap23 NEG: flip sign-seam (max<->min) on other ladder (when meaningful)
    # u23 -> affects m_c_over_m_t, other ladder is d_q_vals, seam uses sign(u_eps)
    # d23 -> affects m_s_over_m_b, other ladder is u_q_vals, seam uses sign(d_eps)
    for sec, other_qvals, eps, key in (
        ("u", d_q_vals, u_eps, "m_c_over_m_t"),
        ("d", u_q_vals, d_eps, "m_s_over_m_b"),
    ):
        if len(other_qvals) >= 2 and key in canonical:
            d_can = int(canonical[key]["d"])
            # canonical kind
            kind_can = "max" if eps >= 0 else "min"
            kind_alt = "min" if kind_can == "max" else "max"
            d_alt = int(_extreme(other_qvals, kind_alt) or d_can)
            p_can = int(canonical[key]["p"])
            if d_alt == d_can:
                issues.append({"type": "neg_gap23_degenerate", "sector": sec, "key": key, "canon_d": d_can, "alt_d": d_alt, "other_q_vals": other_qvals, "eps": eps})
            else:
                blk = cs.get(key) or {}
                cands = blk.get("candidates") or []
                ok = _has_pd(cands, p_can, d_alt)
                if not ok:
                    issues.append({"type": "neg_gap23_pd_missing", "sector": sec, "key": key, "p": p_can, "d_alt": d_alt})
                neg.append({
                    "name": f"NEG_gap23_flip_seam_{sec}",
                    "key": key,
                    "canon": {"p": p_can, "d": d_can, "seam": kind_can},
                    "alt": {"p": p_can, "d": d_alt, "seam": kind_alt},
                    "other_q_vals": other_qvals,
                    "eps": eps,
                    "expect": "DIFF (non-degenerate)" if d_alt != d_can else "DEGENERATE",
                })

    status = "PASS" if not issues else "FAIL"

    out = {
        "version": "v0_1",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "lock": LOCK,
        "derivation_status": "DERIVED",
        "inputs": {
            "quark_proxy": str(qp.relative_to(REPO)).replace("\\", "/"),
            "flavor_ud": str(fl.relative_to(REPO)).replace("\\", "/"),
        },
        "canonical_preferred_pd": canonical,
        "neg_controls": neg,
        "validation": {
            "status": status,
            "issues": issues,
            "note": "NEG controls are *structural*: they must be non-degenerate when ladders have >=2 elements, and the corresponding (p,d) must exist in the candidate space. No facit, no overlay.",
        },
    }

    jp = out_dir / "quark_proxy_neg_core_v0_1.json"
    jp.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {jp}")

    return 0 if status == "PASS" else 10


if __name__ == "__main__":
    raise SystemExit(main())
