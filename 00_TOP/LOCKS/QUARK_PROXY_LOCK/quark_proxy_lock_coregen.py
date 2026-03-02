#!/usr/bin/env python3
"""QUARK_PROXY_LOCK coregen (NO-FACIT).

Build a small, deterministic candidate space for quark ratio proxies.

Inputs (Core only):
  out/CORE_FLAVOR_LOCK/flavor_ud_core_v*.json

Rules:
- MUST NOT read 00_TOP/OVERLAY/** or *reference*.json or any PDG/CODATA/targets.
- Writes only to out/CORE_QUARK_PROXY_LOCK/.

Idea:
- FLAVOR_LOCK emits base ratios per family: r12=m1/m2 and r23=m2/m3.
- Here we generate candidates via facit-free transforms: r^(p)/d, with p,d in {1..6}.

Preferred (v0.2): facit-free, derived from FLAVOR_LOCK's own scan/choice metadata.

We use two internal invariants already present in the Core FLAVOR_LOCK artifact:
  1) sector-local "q" (u.choice.q / d.choice.q) encodes the natural nonlinearity
     for the 12-gap proxy (generation-1 vs generation-2).
  2) the scan-q ladder (scan.u.q_vals / scan.d.q_vals) provides a deterministic
     denominator set for proxy compression; we take the max ladder element for the
     12-gap.
  3) for the 23-gap we use the *opposite* sector's q ladder, with a sign-seam rule
     based on eps_nc sign (scan.*.eps_nc):
        - if eps_nc > 0, pick max(q_vals_other)
        - if eps_nc < 0, pick min(q_vals_other)
     and keep exponent p=1 (linear) for 23-gap.

This remains facit-free: it never reads overlay refs and never scores to PDG.
Compare reports any-hit vs preferred-hit downstream.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[3]


def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _pick_latest(out_dir: Path, pattern: str) -> Optional[Path]:
    cands = sorted(out_dir.glob(pattern))
    return cands[-1] if cands else None


@dataclass(frozen=True)
class Cand:
    id: str
    expr: str
    approx: float
    p: int
    d: int


def _make_candidates(base_expr: str, base_val: float, *, tag: str, preferred_pd: tuple[int, int] | None = None) -> tuple[list[dict], dict]:
    """Generate candidates r^(p)/d for p,d in {1..6}."""
    cands: list[Cand] = []
    k = 0
    for p in range(1, 7):
        for d in range(1, 7):
            k += 1
            expr = f"({base_expr})**{p}/{d}"
            approx = (base_val ** p) / float(d)
            cands.append(Cand(id=f"{tag}{k:03d}", expr=expr, approx=approx, p=p, d=d))

    # deterministic ordering: (p,d) ascending
    cands.sort(key=lambda c: (c.p, c.d))

    out = [
        {"id": c.id, "expr": c.expr, "approx": c.approx, "p": c.p, "d": c.d}
        for c in cands
    ]

    # Default preferred is min complexity (p=1,d=1) unless overridden.
    pref = out[0]
    rule = "min_complexity (p=1,d=1)"

    if preferred_pd is not None:
        p0, d0 = preferred_pd
        for c in out:
            if int(c.get("p")) == int(p0) and int(c.get("d")) == int(d0):
                pref = c
                rule = f"derived_preferred (p={p0},d={d0})"
                break

    preferred = {"id": pref["id"], "expr": pref["expr"], "approx": pref["approx"], "p": int(pref["p"]), "d": int(pref["d"]), "rule": rule}
    return out, preferred


def _extreme(vals: list[int], *, kind: str) -> Optional[int]:
    if not vals:
        return None
    if kind == "min":
        return min(int(x) for x in vals)
    if kind == "max":
        return max(int(x) for x in vals)
    raise ValueError(kind)


def main() -> int:
    out_dir = REPO / "out" / "CORE_QUARK_PROXY_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    src_dir = REPO / "out" / "CORE_FLAVOR_LOCK"
    src = _pick_latest(src_dir, "flavor_ud_core_v*.json")
    if not src or not src.exists():
        raise SystemExit("Missing Core FLAVOR_LOCK artifact: out/CORE_FLAVOR_LOCK/flavor_ud_core_v*.json")

    obj = _read_json(src)

    u = obj.get("u") or {}
    d = obj.get("d") or {}
    ur = (u.get("ratios") or {})
    dr = (d.get("ratios") or {})

    scan = obj.get("scan") or {}
    su = scan.get("u") or {}
    sd = scan.get("d") or {}

    # Base ratios
    u12 = float(ur.get("m1_over_m2"))
    u23 = float(ur.get("m2_over_m3"))
    d12 = float(dr.get("m1_over_m2"))
    d23 = float(dr.get("m2_over_m3"))

    # Metadata (Core-only; used for facit-free preferred selection)
    u_choice = (u.get("choice") or {})
    d_choice = (d.get("choice") or {})

    u_q_choice = int(u_choice.get("q", 1))
    d_q_choice = int(d_choice.get("q", 1))

    u_q_vals = [int(x) for x in (su.get("q_vals") or []) if isinstance(x, (int, float))]
    d_q_vals = [int(x) for x in (sd.get("q_vals") or []) if isinstance(x, (int, float))]

    u_eps = float(su.get("eps_nc", 0.0))
    d_eps = float(sd.get("eps_nc", 0.0))

    # Preferred denominators/exponents (facit-free)
    # 12-gap: exponent from choice.q, denom from max(scan.q_vals)
    u12_pd = (u_q_choice, _extreme(u_q_vals, kind="max") or 1)
    d12_pd = (d_q_choice, _extreme(d_q_vals, kind="max") or 1)

    # 23-gap: exponent fixed to 1, denom from *opposite* sector q ladder with sign-seam.
    # sign-seam: eps_nc>0 -> pick max(other); eps_nc<0 -> pick min(other)
    u23_den = _extreme(d_q_vals, kind=("max" if u_eps >= 0 else "min")) or 1
    d23_den = _extreme(u_q_vals, kind=("max" if d_eps >= 0 else "min")) or 1
    u23_pd = (1, u23_den)
    d23_pd = (1, d23_den)

    # Candidate sets
    u12_cands, u12_pref = _make_candidates("u_r12", u12, tag="U12_", preferred_pd=u12_pd)
    u23_cands, u23_pref = _make_candidates("u_r23", u23, tag="U23_", preferred_pd=u23_pd)
    d12_cands, d12_pref = _make_candidates("d_r12", d12, tag="D12_", preferred_pd=d12_pd)
    d23_cands, d23_pref = _make_candidates("d_r23", d23, tag="D23_", preferred_pd=d23_pd)

    # Semantic gate (Core-only sanity): hierarchy should hold for the base ratios
    semantic = {
        "base_hierarchy": {
            "u": {"r12": u12, "r23": u23, "ok": (0 < u12 < 1 and 0 < u23 < 1)},
            "d": {"r12": d12, "r23": d23, "ok": (0 < d12 < 1 and 0 < d23 < 1)},
        },
        "note": "Semantic gate is purely internal: base ratios must be (0,1) and represent a strict hierarchy m1<m2<m3 in proxy-space.",
    }

    out = {
        "version": "v0.2",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "inputs": {"flavor_ud": str(src.relative_to(REPO)).replace("\\", "/")},
        "base": {
            "u": {"r12": u12, "r23": u23},
            "d": {"r12": d12, "r23": d23},
        },
        "semantic_gate": semantic,
        "preferred_rule": {
            "gap12": {
                "u": {"p": u12_pd[0], "d": u12_pd[1], "from": {"choice.q": u_q_choice, "scan.u.q_vals": u_q_vals}},
                "d": {"p": d12_pd[0], "d": d12_pd[1], "from": {"choice.q": d_q_choice, "scan.d.q_vals": d_q_vals}},
            },
            "gap23": {
                "u": {"p": 1, "d": u23_den, "from": {"other": "d", "scan.d.q_vals": d_q_vals, "sign_seam": ("max" if u_eps >= 0 else "min"), "scan.u.eps_nc": u_eps}},
                "d": {"p": 1, "d": d23_den, "from": {"other": "u", "scan.u.q_vals": u_q_vals, "sign_seam": ("max" if d_eps >= 0 else "min"), "scan.d.eps_nc": d_eps}},
            },
            "note": "Preferred selection is deterministic and uses only Core FLAVOR_LOCK metadata (choice.q, scan.q_vals, scan.eps_nc).",
        },
        "candidate_space": {
            "m_u_over_m_c": {"type": "derived_candidate_set", "base": "u.r12", "candidates": u12_cands, "preferred": u12_pref},
            "m_c_over_m_t": {"type": "derived_candidate_set", "base": "u.r23", "candidates": u23_cands, "preferred": u23_pref},
            "m_d_over_m_s": {"type": "derived_candidate_set", "base": "d.r12", "candidates": d12_cands, "preferred": d12_pref},
            "m_s_over_m_b": {"type": "derived_candidate_set", "base": "d.r23", "candidates": d23_cands, "preferred": d23_pref},
            "note": "Derived candidates are r^(p)/d with p,d in {1..6}. Preferred is facit-free and derived from FLAVOR_LOCK metadata.",
        },
    }

    p = out_dir / "quark_proxy_core_v0_2.json"
    p.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
