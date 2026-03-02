#!/usr/bin/env python3
"""ENERGY_ANCHOR_FREEZE (v0.1)

Creates (or verifies) an Overlay freeze record for the *single* energy anchor.

Policy:
  - Exactly one energy anchor may be enabled in Overlay.
  - Once frozen, subsequent runs must match the frozen (anchor_id, value, unit).
  - Core remains dimensionless; this is Overlay bookkeeping.

Usage (repo root):
  python3 00_TOP/OVERLAY/energy_anchor_freeze.py

Outputs:
  00_TOP/OVERLAY/ENERGY_ANCHOR_FREEZE_2026-02-14.json

Exit codes:
  0 = created or verified OK
  2 = FAIL (missing ref, disabled, mismatch)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


FREEZE_NAME = "ENERGY_ANCHOR_FREEZE_2026-02-14.json"


def _repo_root_from_here(here: Path) -> Path:
    return here.resolve().parents[2]


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _load_json(p: Path) -> dict:
    return json.loads(_read_text(p))


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _write_json(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    here = Path(__file__).resolve()
    repo = _repo_root_from_here(here)

    ref_path = repo / "00_TOP/OVERLAY/energy_anchor_reference.json"
    freeze_path = repo / f"00_TOP/OVERLAY/{FREEZE_NAME}"

    if not ref_path.exists():
        _write_json(freeze_path, {
            "version": "v0.1",
            "gate": {"pass": False, "reason": "missing_energy_anchor_reference"},
            "missing": [str(ref_path.relative_to(repo))],
        })
        return 2

    ref_txt = _read_text(ref_path)
    ref = _load_json(ref_path)

    enabled = bool(ref.get("enabled", False))
    anchor_id = str(ref.get("anchor_id", ""))
    anchor_value = ref.get("anchor_value", None)
    unit = str(ref.get("unit", ""))

    if not (enabled and anchor_id and isinstance(anchor_value, (int, float)) and unit):
        _write_json(freeze_path, {
            "version": "v0.1",
            "gate": {"pass": False, "reason": "anchor_disabled_or_invalid"},
            "ref": {"enabled": enabled, "anchor_id": anchor_id, "anchor_value": anchor_value, "unit": unit},
            "ref_sha256": _sha256_text(ref_txt),
        })
        return 2

    # If freeze exists, verify match; else create.
    if freeze_path.exists():
        fr = _load_json(freeze_path)
        frozen = fr.get("frozen", {}) if isinstance(fr, dict) else {}
        ok = (
            frozen.get("anchor_id") == anchor_id
            and float(frozen.get("anchor_value")) == float(anchor_value)
            and frozen.get("unit") == unit
        )
        if ok:
            fr["gate"] = {"pass": True, "reason": "match"}
            fr["ref_sha256"] = _sha256_text(ref_txt)
            _write_json(freeze_path, fr)
            return 0
        _write_json(freeze_path, {
            "version": "v0.1",
            "gate": {"pass": False, "reason": "freeze_mismatch"},
            "frozen": frozen,
            "ref": {"enabled": enabled, "anchor_id": anchor_id, "anchor_value": anchor_value, "unit": unit},
            "ref_sha256": _sha256_text(ref_txt),
        })
        return 2

    _write_json(freeze_path, {
        "version": "v0.1",
        "gate": {"pass": True, "reason": "created"},
        "frozen": {"anchor_id": anchor_id, "anchor_value": float(anchor_value), "unit": unit},
        "ref_sha256": _sha256_text(ref_txt),
        "notes": "Overlay freeze record for exactly one energy anchor. Core remains dimensionless.",
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
