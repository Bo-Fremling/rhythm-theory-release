#!/usr/bin/env python3
"""LEPTON_ENGAGEMENT_LOCK coregen (NO-FACIT).

Inputs:
  out/CORE_FLAVOR_LOCK/flavor_enu_core_v0_9.json
Outputs:
  out/CORE_LEPTON_ENGAGEMENT_LOCK/lepton_engagement_lock_core_v0_1.json
  out/CORE_LEPTON_ENGAGEMENT_LOCK/lepton_engagement_lock_core_summary_v0_1.md
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

LSTAR = 1260
STEP = 6


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    inp = REPO_ROOT / "out" / "CORE_FLAVOR_LOCK" / "flavor_enu_core_v0_9.json"
    if not inp.exists():
        print(f"MISSING: {inp}")
        return 2

    obj = load_json(inp)
    r = (((obj.get("e", {}) or {}).get("ratios", {}) or {}))
    r12 = float(r.get("m1_over_m2"))
    r23 = float(r.get("m2_over_m3"))

    best = None
    best_key = None

    Ns = list(range(STEP, LSTAR + 1, STEP))

    for N1 in Ns:
        for N2 in Ns:
            if N2 < N1:
                continue
            e12 = (N1 / N2 - r12) ** 2
            if best_key is not None and e12 > best_key[0]:
                continue
            for N3 in Ns:
                if N3 < N2:
                    continue
                e = e12 + (N2 / N3 - r23) ** 2
                key = (e, N3, N2, N1)
                if best is None or key < best_key:
                    best = (N1, N2, N3)
                    best_key = key

    assert best is not None and best_key is not None
    N1, N2, N3 = best

    out = {
        "version": "v0.1",
        "policy": {"L_star": LSTAR, "step": STEP, "require_multiple_of_6": True},
        "inputs": {"flavor_core": str(inp.relative_to(REPO_ROOT)).replace("\\", "/"), "r12": r12, "r23": r23},
        "best": {
            "N_act": {"e": int(N1), "mu": int(N2), "tau": int(N3)},
            "ratios_pred": {"m1_over_m2": N1 / N2, "m2_over_m3": N2 / N3},
            "residuals": {"dr12": N1 / N2 - r12, "dr23": N2 / N3 - r23},
            "cost": float(best_key[0]),
        },
        "derivation_status": "CANDIDATE-SET",
        "validation_status": "UNTESTED",
    }

    out_dir = REPO_ROOT / "out" / "CORE_LEPTON_ENGAGEMENT_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    jpath = out_dir / "lepton_engagement_lock_core_v0_1.json"
    jpath.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    spath = out_dir / "lepton_engagement_lock_core_summary_v0_1.md"
    spath.write_text(
        "\n".join(
            [
                "# LEPTON_ENGAGEMENT_LOCK core summary (v0.1)",
                "",
                f"Input ratios (Core) from {out['inputs']['flavor_core']}: r12={r12:.12g}, r23={r23:.12g}",
                "",
                "Best discrete N_act (multiples of 6, <=1260):",
                f"- N_e_act={N1}",
                f"- N_mu_act={N2}",
                f"- N_tau_act={N3}",
                "",
                "Predicted ratios:",
                f"- N1/N2={N1/N2:.12g}  (dr12={N1/N2 - r12:+.3e})",
                f"- N2/N3={N2/N3:.12g}  (dr23={N2/N3 - r23:+.3e})",
                "",
                f"Cost: {best_key[0]:.6e}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"WROTE: {jpath}")
    print(f"WROTE: {spath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
