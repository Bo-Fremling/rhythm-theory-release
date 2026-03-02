#!/usr/bin/env python3
"""NU_MECHANISM_LOCK (v0.3)

Core-only neutrino scaffold.

Policy:
  - This runner MUST NOT read Overlay reference files.
  - It outputs only dimensionless quantities.
  - Any mapping to eV (and any PDG range checks) belongs to verify/report.

Core:
  epsilon = L_cap/L_star = 7/1260 = 1/180
  s_nu = sextet * epsilon^4

Outputs:
  out/CORE_NU_MECHANISM_LOCK/nu_mechanism_lock_v0_3.json
  out/CORE_NU_MECHANISM_LOCK/nu_mechanism_lock_summary_v0_3.md

Exit codes:
  0 PASS (core gates)
  2 FAIL (core gate fail)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

VERSION = "v0_3"
LSTAR = 1260
LCAP = 7
SEXTET = 6

PATTERNS = [
    {"id": "A", "n": [0, 3, 17], "note": "minimal m1=0; Δm²31/Δm²21 = 289/9 exactly"},
    {"id": "B", "n": [1, 3, 17], "note": "nonzero m1"},
]


def _pattern_key(p: dict) -> tuple[int, int, int, int, int]:
    """Internal (facit-free) tie-break for pattern preference.

    Prefer:
      1) exact small-rational Δm² ratio gate (289/9) if present
      2) minimal n0 (m1=0 is simplest)
      3) minimal total integer complexity

    Returns tuple where lower is better.
    """
    n = p.get("n") or [999, 999, 999]
    if not (isinstance(n, list) and len(n) == 3):
        return (9, 9, 9, 9, 9)
    n0, n1, n2 = int(n[0]), int(n[1]), int(n[2])
    num = (n2 * n2) - (n0 * n0)
    den = (n1 * n1) - (n0 * n0)
    exact_gate = 0 if (num == 289 and den == 9) else 1
    return (exact_gate, 0 if n0 == 0 else 1, n0 + n1 + n2, n0, n1)


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
    return x == x and x > 0.0 and x != float("inf")


def _epsilon() -> float:
    return float(LCAP) / float(LSTAR)


def _core_gates(eps: float) -> Dict[str, bool]:
    # v0.2: add an exact rational gate for Pattern A.
    # For A: n=[0,3,17] => Δm²31/Δm²21 = (17^2-0^2)/(3^2-0^2) = 289/9.
    ratio_ok = False
    for p in PATTERNS:
        if p.get("id") == "A":
            n = p.get("n")
            if isinstance(n, list) and len(n) == 3 and n[0] == 0 and n[1] == 3 and n[2] == 17:
                num = (n[2] * n[2]) - (n[0] * n[0])
                den = (n[1] * n[1]) - (n[0] * n[0])
                ratio_ok = (num == 289 and den == 9)
            break

    return {
        "epsilon_exact_1_over_180": abs(eps - (1.0 / 180.0)) < 1e-15,
        "s_nu_positive": _finite_pos(SEXTET * (eps ** 4)),
        "pattern_ordering": all((p["n"][2] > p["n"][1] > 0) for p in PATTERNS),
        "pattern_A_ratio_exact_289_over_9": ratio_ok,
    }

def _pattern_metrics_dimless(eps: float, n: list[int]) -> Dict[str, Any]:
    """Dimensionless neutrino pattern in units of m_e."""
    s_nu = float(SEXTET) * (eps ** 4)
    m0_over_me = s_nu
    m_over_me = [float(ni) * m0_over_me for ni in n]
    dm21 = (m_over_me[1] ** 2) - (m_over_me[0] ** 2)
    dm31 = (m_over_me[2] ** 2) - (m_over_me[0] ** 2)
    ratio = (dm31 / dm21) if dm21 != 0 else None

    num = (n[2] * n[2]) - (n[0] * n[0])
    den = (n[1] * n[1]) - (n[0] * n[0])

    return {
        "s_nu": s_nu,
        "m0_over_m_e": m0_over_me,
        "m_over_m_e": m_over_me,
        "delta_m2_over_m_e2": {"dm21": dm21, "dm31": dm31, "dm31_over_dm21": ratio},
        "delta_m2_ratio_exact": {"num": int(num), "den": int(den), "value": (float(num) / float(den)) if den != 0 else None},
    }


def main() -> int:
    here = Path(__file__).resolve()
    repo = _repo_root_from_here(here)

    out_json = repo / f"out/CORE_NU_MECHANISM_LOCK/nu_mechanism_lock_{VERSION}.json"
    out_md = repo / f"out/CORE_NU_MECHANISM_LOCK/nu_mechanism_lock_summary_{VERSION}.md"

    eps = _epsilon()
    gates = _core_gates(eps)
    ok = all(gates.values())

    # deterministic preference (still keeps full candidate-set)
    patt_sorted = sorted(PATTERNS, key=_pattern_key)
    preferred_id = patt_sorted[0]["id"] if patt_sorted else None

    patterns_out = []
    for p in patt_sorted:
        metrics = _pattern_metrics_dimless(eps, p["n"])
        status = "DERIVED" if (p.get("id") == preferred_id) else "CANDIDATE-SET"
        patterns_out.append({
            "id": p["id"],
            "n": p["n"],
            "note": p.get("note"),
            "pattern_status": status,
            **metrics,
        })

    obj = {
        "version": VERSION,
        "derivation_status": "CANDIDATE-SET",
        "validation_status": "UNTESTED",
        "policy": {
            "core_only": True,
            "reads_overlay": False,
            "outputs_dimensionless_only": True,
        },
        "core": {
            "L_star": LSTAR,
            "L_cap": LCAP,
            "sextet": SEXTET,
            "epsilon": eps,
            "s_nu": float(SEXTET) * (eps ** 4),
            "patterns": [{"id": p["id"], "n": p["n"], "note": p.get("note")} for p in PATTERNS],
            "derived": {
                "epsilon_exact": {"num": LCAP, "den": LSTAR, "as_str": "1/180"},
                "pattern_A_delta_m2_ratio": {"num": 289, "den": 9, "value": 289.0 / 9.0},
            },
        },
        "gates": gates,
        "gate": {"pass": bool(ok), "reason": "ok" if ok else "core_gate_fail"},
        "results": {
            "selection": {
                "preferred_pattern_id": preferred_id,
                "tie_break": "Prefer exact rational gate (289/9), then minimal n0, then minimal integer complexity.",
                "note": "Preference is Core-internal and facit-free; non-preferred patterns are retained as candidates.",
            },
            "patterns": patterns_out,
        },
        "notes": [
            "v0.3 is Core-only: outputs are strictly dimensionless (relative to m_e).",
            "v0.3 keeps the exact rational gate for Pattern A: Δm²31/Δm²21 = 289/9.",
            "Any absolute-energy mapping belongs to verify/report (Overlay).",
        ],
    }

    _write_json(out_json, obj)

    # Markdown summary
    lines = [
        "# NU_MECHANISM_LOCK v0.3 (Core-only)",
        "",
        f"Overall: {'PASS' if ok else 'FAIL'}",
        "",
        "## Core",
        "",
        f"- L*: {LSTAR}",
        f"- L_cap: {LCAP}",
        f"- epsilon = L_cap/L*: {eps} (target 1/180)",
        f"- sextet: {SEXTET}",
        f"- s_nu = 6*epsilon^4: {float(SEXTET) * (eps ** 4)}",
        f"- Pattern A exact ratio: Δm²31/Δm²21 = 289/9 = {289.0/9.0}",
        "",
        "## Gates",
        "",
    ]
    for k, v in gates.items():
        lines.append(f"- {k}: {'PASS' if v else 'FAIL'}")

    lines += [
        "",
        "## Pattern outputs (dimensionless; units of m_e)",
        "",
    ]

    for p in patterns_out:
        m = p["m_over_m_e"]
        dm = p["delta_m2_over_m_e2"]
        rat = p.get("delta_m2_ratio_exact") or {}
        rat_str = f"{rat.get('num')}/{rat.get('den')}" if (rat.get('num') is not None and rat.get('den') is not None) else "?"
        lines.append(f"### Pattern {p['id']} ({p.get('pattern_status')}) n={p['n']} ({p.get('note','')})")
        lines.append("")
        lines.append(f"- m0/m_e: {p['m0_over_m_e']}")
        lines.append(f"- m/m_e: [{m[0]}, {m[1]}, {m[2]}]")
        lines.append(f"- Δm²21/m_e²: {dm['dm21']}")
        lines.append(f"- Δm²31/m_e²: {dm['dm31']}")
        lines.append(f"- ratio (31/21): {dm['dm31_over_dm21']} (exact {rat_str})")
        lines.append("")

    _write_text(out_md, "\n".join(lines) + "\n")

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
