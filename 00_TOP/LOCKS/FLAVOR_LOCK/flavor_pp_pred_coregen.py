#!/usr/bin/env python3
"""FLAVOR_LOCK PP-pred coregen (NO-FACIT).

Goal
  Generate a Core-safe PP-based CKM/PMNS prediction artifact under out/CORE_FLAVOR_LOCK/,
  WITHOUT importing any precomputed out/FLAVOR_LOCK/flavor_pp_pred*.json.

How
  - Use ONLY Core artifacts as inputs:
      out/CORE_FLAVOR_LOCK/flavor_ud_core_v0_9.json
      out/CORE_FLAVOR_LOCK/flavor_enu_core_v0_9.json
  - Reuse the existing deterministic verifier + PP-predictor logic by temporarily
    stubbing out/FLAVOR_LOCK as a scratch directory populated with Core inputs.
  - Overlay refs are never used; under InfluenceAudit the overlay folder is stubbed away.

Writes
  - out/CORE_FLAVOR_LOCK/flavor_pp_pred_core_v0_1.json
  - out/CORE_FLAVOR_LOCK/flavor_pp_pred_core_summary_v0_1.md

Policy
  - MUST NOT read Overlay/** or *reference*.json.
  - No scan, no optimization, no scoring against PDG/CODATA.
  - Deterministic preference lists live in flavor_lock_pp_predict.py (internal policy).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


REPO = Path(__file__).resolve().parents[3]


def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def _sha256_file(p: Path) -> str:
    return _sha256_bytes(p.read_bytes())


def _read_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: Path, obj: Dict[str, Any]) -> None:
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8")


def main() -> int:
    core_dir = REPO / "out" / "CORE_FLAVOR_LOCK"
    ud_src = core_dir / "flavor_ud_core_v0_9.json"
    enu_src = core_dir / "flavor_enu_core_v0_9.json"
    if not ud_src.exists() or not enu_src.exists():
        raise SystemExit("missing Core flavor inputs; run flavor_lock_coregen.py first")

    # Fast path: if an existing Core-hosted PP-pred artefact matches the input
    # hashes, reuse it to keep the Core suite runtime bounded.
    out_json = core_dir / "flavor_pp_pred_core_v0_1.json"
    out_md = core_dir / "flavor_pp_pred_core_summary_v0_1.md"
    if out_json.exists() and out_md.exists():
        try:
            prev = _read_json(out_json)
            prov = (prev.get("provenance") or {}).get("inputs") or {}
            h_ud = _sha256_file(ud_src)
            h_enu = _sha256_file(enu_src)
            k_ud = str(ud_src.relative_to(REPO)).replace("\\", "/")
            k_enu = str(enu_src.relative_to(REPO)).replace("\\", "/")
            if prov.get(k_ud) == h_ud and prov.get(k_enu) == h_enu:
                print(f"REUSED: {out_json}")
                return 0
        except Exception:
            pass

    # Scratch FLAVOR_LOCK directory (we never keep outputs here; only used to reuse existing code).
    out_root = REPO / "out"
    flv = out_root / "FLAVOR_LOCK"
    bak = None

    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    try:
        if flv.exists():
            bak = out_root / f"FLAVOR_LOCK__BACKUP__{stamp}"
            flv.rename(bak)

        flv.mkdir(parents=True, exist_ok=True)

        # Populate scratch inputs with Core material under expected filenames.
        ud_tmp = flv / "flavor_ud_v0_9.json"
        enu_tmp = flv / "flavor_enu_v0_9.json"
        shutil.copy2(ud_src, ud_tmp)
        shutil.copy2(enu_src, enu_tmp)

        # Run deterministic verify + PP predict (no overlay needed).
        # These modules are local files in this directory.
        import flavor_lock_verify  # type: ignore
        import flavor_lock_pp_predict  # type: ignore

        rc1 = flavor_lock_verify.main()
        if rc1 not in (0, 1):  # 0=PASS, 1=FAIL (core gates), 2=missing
            raise SystemExit(f"verify returned rc={rc1}")

        rc2 = flavor_lock_pp_predict.main()
        if rc2 != 0:
            raise SystemExit(f"pp_predict returned rc={rc2}")

        pred_p = flv / "flavor_pp_pred_v0_1.json"
        if not pred_p.exists():
            raise SystemExit("pp_predict did not write flavor_pp_pred_v0_1.json")

        pred = _read_json(pred_p)

        # Package as Core-hosted artifact.
        out_dir = core_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        out_json = out_dir / "flavor_pp_pred_core_v0_1.json"
        out_md = out_dir / "flavor_pp_pred_core_summary_v0_1.md"

        packaged: Dict[str, Any] = {
            "version": "core_pp_pred_v0_2",
            "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "policy": {
                "no_facit": True,
                "no_overlay_reads": True,
                "no_scan": True,
                "scratch_flavor_lock": True,
                "note": "Generated from Core flavor artifacts via deterministic verify+pp_predict.",
            },
            "provenance": {
                "inputs": {
                    str(ud_src.relative_to(REPO)).replace("\\", "/"): _sha256_file(ud_src),
                    str(enu_src.relative_to(REPO)).replace("\\", "/"): _sha256_file(enu_src),
                },
                "scratch_dir": str(flv.relative_to(REPO)).replace("\\", "/"),
                "scratch_outputs": {
                    "verify_json": "out/FLAVOR_LOCK/flavor_lock_verify_v0_1.json",
                    "pp_pred_json": "out/FLAVOR_LOCK/flavor_pp_pred_v0_1.json",
                },
                "picked_key": pred.get("picked_key"),
                "picked_key_ckm": pred.get("picked_key_ckm"),
                "picked_key_pmns": pred.get("picked_key_pmns"),
            },
            "CKM": pred.get("CKM") or {},
            "PMNS": pred.get("PMNS") or {},
            "notes": list(pred.get("notes") or []) + [
                "Core-hosted PP-pred; computed (not imported). ",
            ],
        }

        _write_json(out_json, packaged)

        ck = (packaged.get("CKM") or {}).get("angles") or {}
        pm = (packaged.get("PMNS") or {}).get("angles") or {}

        def _fmt(a: dict) -> str:
            def f(k: str) -> str:
                v = a.get(k)
                return "—" if v is None else f"{float(v):.6g}"
            return (
                f"θ12={f('theta12_deg')}°, θ23={f('theta23_deg')}°, θ13={f('theta13_deg')}°, "
                f"δ≈{f('delta_deg_from_sin')}°, J={f('J')}"
            )

        md = []
        md.append("# FLAVOR_LOCK PP prediction (Core-hosted v0.2)\n")
        md.append("## Provenance\n")
        for k, v in packaged["provenance"]["inputs"].items():
            md.append(f"- input: `{k}` sha256=`{v}`")
        md.append(f"- picked_key_ckm: `{packaged['provenance'].get('picked_key_ckm')}`")
        md.append(f"- picked_key_pmns: `{packaged['provenance'].get('picked_key_pmns')}`\n")
        md.append("## CKM (pred)\n")
        md.append("- " + _fmt(ck) + "\n")
        md.append("## PMNS (pred)\n")
        md.append("- " + _fmt(pm) + "\n")
        _write_text(out_md, "\n".join(md) + "\n")

        print(f"WROTE: {out_json}")
        return 0

    finally:
        # Always restore original out/FLAVOR_LOCK
        try:
            if flv.exists():
                shutil.rmtree(flv)
        except Exception:
            pass
        if bak is not None and bak.exists():
            bak.rename(flv)


if __name__ == "__main__":
    raise SystemExit(main())
