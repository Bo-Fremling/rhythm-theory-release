#!/usr/bin/env python3
"""Promote SM29 status entries ONLY when verifiers PASS.

Policy:
- No new physics. No tuning.
- Promotion is purely bookkeeping based on machine-checkable verifier artifacts.

Usage (repo root):
  python3 00_TOP/LOCKS/SM_PARAM_INDEX/sm29_promote_verified.py

Inputs (optional verifiers):
  out/FLAVOR_LOCK/flavor_lock_verify_v0_1.json
  out/EM_LOCK/em_lock_verify_v0_1.json
  out/ENERGY_ANCHOR_LOCK/energy_anchor_lock_v0_2.json (or v0_1)
  00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_PARAMETERS_STATUS.md

Outputs:
  (updated) 00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_PARAMETERS_STATUS.md
  out/SM_PARAM_INDEX/sm29_promotion_log_v0_2.json

Exit codes:
  0 = ran (applied or noop)
  2 = missing required status table
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[3]

FLAVOR_VERIFY = REPO_ROOT / "out/FLAVOR_LOCK/flavor_lock_verify_v0_1.json"
EM_VERIFY     = REPO_ROOT / "out/EM_LOCK/em_lock_verify_v0_1.json"
ENERGY_ANCHOR_VERIFY_CAND = [
    REPO_ROOT / "out/ENERGY_ANCHOR_LOCK/energy_anchor_lock_v0_3.json",
    REPO_ROOT / "out/ENERGY_ANCHOR_LOCK/energy_anchor_lock_v0_2.json",
    REPO_ROOT / "out/ENERGY_ANCHOR_LOCK/energy_anchor_lock_v0_1.json",
]
STATUS_MD     = REPO_ROOT / "00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_PARAMETERS_STATUS.md"
OUT_DIR       = REPO_ROOT / "out/SM_PARAM_INDEX"

PROMOTIONS_FLAVOR = {
    "CKM vinkel 1": "PASS (CORE)",
    "CKM vinkel 2": "PASS (CORE)",
    "CKM vinkel 3": "PASS (CORE)",
    "CKM CP‑fas": "PASS (CORE)",
    "PMNS vinkel 1": "PASS (CORE)",
    "PMNS vinkel 2": "PASS (CORE)",
    "PMNS vinkel 3": "PASS (CORE)",
    "PMNS CP‑fas": "PASS (CORE)",
}

PROMOTIONS_EM = {
    "EM‑koppling (α)": "PASS (OVERLAY)",
}


def _energy_anchor_promotions(ea_obj: Dict) -> Dict[str, str]:
    """Return promotions for absolute fermion masses based on which sector was anchored."""
    anc = ea_obj.get("anchor", {})
    sec = anc.get("anchor_sector")
    scope = (ea_obj.get("policy", {}) or {}).get("scope", anc.get("scope"))
    if isinstance(scope, str) and scope.strip().lower() == "global":
        # One anchor => one energy scale for all charged sectors (u,d,e).
        return {
            "Elektronmassa": "PASS (OVERLAY)",
            "Muonmassa": "PASS (OVERLAY)",
            "Taumassa": "PASS (OVERLAY)",
            "Up‑kvarkmassa": "PASS (OVERLAY)",
            "Charm‑kvarkmassa": "PASS (OVERLAY)",
            "Top‑kvarkmassa": "PASS (OVERLAY)",
            "Down‑kvarkmassa": "PASS (OVERLAY)",
            "Strange‑kvarkmassa": "PASS (OVERLAY)",
            "Bottom‑kvarkmassa": "PASS (OVERLAY)",
        }
    if not isinstance(sec, str):
        return {}
    sec = sec.strip()
    if sec == "e":
        return {
            "Elektronmassa": "PASS (OVERLAY)",
            "Muonmassa": "PASS (OVERLAY)",
            "Taumassa": "PASS (OVERLAY)",
        }
    if sec == "u":
        return {
            "Up‑kvarkmassa": "PASS (OVERLAY)",
            "Charm‑kvarkmassa": "PASS (OVERLAY)",
            "Top‑kvarkmassa": "PASS (OVERLAY)",
        }
    if sec == "d":
        return {
            "Down‑kvarkmassa": "PASS (OVERLAY)",
            "Strange‑kvarkmassa": "PASS (OVERLAY)",
            "Bottom‑kvarkmassa": "PASS (OVERLAY)",
        }
    return {}


def _load_json(p: Path) -> Dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _extract_gate_pass(obj: Dict) -> bool:
    g = obj.get("gate", {})
    return bool(g.get("PASS", g.get("pass", False)))


def _edit_table_lines(lines: List[str], promotions: Dict[str, str]) -> Tuple[List[str], List[Dict]]:
    """Return (new_lines, changes)."""
    changes: List[Dict] = []
    new_lines: List[str] = []

    for line in lines:
        if not line.startswith("|"):
            new_lines.append(line)
            continue

        # Parse markdown table row: | Param | RT | RT ger | Kräver |
        parts = [p.strip() for p in line.strip().split("|")]
        # parts[0] and parts[-1] are empty due to leading/trailing pipe
        if len(parts) < 5:
            new_lines.append(line)
            continue

        param = parts[1]
        rt_status = parts[2]

        if param in promotions:
            target = promotions[param]
            if rt_status != target:
                changes.append({"param": param, "from": rt_status, "to": target})
                parts[2] = target
                # Reconstruct with single spaces around cells
                rebuilt = "| " + " | ".join(parts[1:-1]) + " |\n"
                new_lines.append(rebuilt)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    return new_lines, changes


def main() -> int:
    if not STATUS_MD.exists():
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "sm29_promotion_log_v0_2.json").write_text(
            json.dumps({"version": "v0.2", "status": "MISSING", "missing": [str(STATUS_MD.relative_to(REPO_ROOT))]}, indent=2),
            encoding="utf-8",
        )
        return 2

    # Load optional verifiers
    fv = _load_json(FLAVOR_VERIFY) if FLAVOR_VERIFY.exists() else None
    ev = _load_json(EM_VERIFY) if EM_VERIFY.exists() else None
    ea_path = next((p for p in ENERGY_ANCHOR_VERIFY_CAND if p.exists()), None)
    ea = _load_json(ea_path) if ea_path is not None else None

    flavor_pass = _extract_gate_pass(fv) if isinstance(fv, dict) else False
    em_pass = _extract_gate_pass(ev) if isinstance(ev, dict) else False
    energy_pass = bool(ea and isinstance(ea.get("gate", {}), dict) and ea.get("gate", {}).get("pass", False))

    promotions: Dict[str, str] = {}
    if flavor_pass:
        promotions.update(PROMOTIONS_FLAVOR)
    if em_pass:
        promotions.update(PROMOTIONS_EM)
    if energy_pass:
        promotions.update(_energy_anchor_promotions(ea))

    lines = STATUS_MD.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines, changes = _edit_table_lines(lines, promotions)

    STATUS_MD.write_text("".join(new_lines), encoding="utf-8")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "sm29_promotion_log_v0_2.json").write_text(
        json.dumps({
            "version": "v0.2",
            "status": "APPLIED" if changes else "NOOP",
            "inputs": {
                "flavor_verify": str(FLAVOR_VERIFY.relative_to(REPO_ROOT)) if FLAVOR_VERIFY.exists() else None,
                "em_verify": str(EM_VERIFY.relative_to(REPO_ROOT)) if EM_VERIFY.exists() else None,
                "energy_anchor_lock": str(ea_path.relative_to(REPO_ROOT)) if ea_path is not None else None,
                "status_md": str(STATUS_MD.relative_to(REPO_ROOT)),
            },
            "gates": {
                "flavor_pass": flavor_pass,
                "em_pass": em_pass,
                "energy_anchor_pass": energy_pass,
            },
            "promotions_applied": sorted(promotions.keys()),
            "changes": changes,
        }, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
