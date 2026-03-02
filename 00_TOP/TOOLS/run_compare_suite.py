#!/usr/bin/env python3
"""Run the compare suite (Overlay-only).

Purpose
- Run all *_compare.py scripts in a fixed order.
- Produce a small audit summary (exit codes + tails).

Rules
- This runner MUST NOT be used as Core input.
- It does not stub overlay.

Writes
- out/COMPARE_AUDIT/compare_suite_run_v0_1_<stamp>.json
- out/COMPARE_AUDIT/compare_suite_run_v0_1_<stamp>.md

v0.2: optional chunking (--start/--count) for environments with strict execution
      time limits.
"""

from __future__ import annotations

import json
import subprocess
import sys
import argparse
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

COMPARE_ORDER = [
    "00_TOP/LOCKS/EM_LOCK/em_lock_compare.py",
    "00_TOP/LOCKS/EW_COUPLING_LOCK/ew_coupling_lock_compare.py",
    "00_TOP/LOCKS/GS_LOCK/gs_lock_compare.py",
    "00_TOP/LOCKS/FLAVOR_LOCK/flavor_lock_compare.py",
    "00_TOP/LOCKS/LEPTON_ENGAGEMENT_LOCK/lepton_engagement_lock_compare.py",
    "00_TOP/LOCKS/LEPTON_MASS_LOCK/lepton_mass_lock_compare.py",
    "00_TOP/LOCKS/NU_MECHANISM_LOCK/nu_mechanism_lock_compare.py",
    "00_TOP/LOCKS/THETA_QCD_LOCK/theta_qcd_lock_compare.py",
    "00_TOP/LOCKS/HIGGS_VEV_LOCK/higgs_vev_lock_compare.py",
    "00_TOP/LOCKS/TOP_PROXY_LOCK/top_proxy_lock_compare.py",
    "00_TOP/LOCKS/ENERGY_ANCHOR_LOCK/energy_anchor_lock_compare.py",
    "00_TOP/LOCKS/HADRON_PROXY_LOCK/hadron_proxy_lock_compare.py",
    "00_TOP/LOCKS/PPN_LOCK/ppn_lock_compare.py",
    "00_TOP/LOCKS/SM_PARAM_INDEX/sm29_index_compare.py",
]


def _run_one(script_rel: str) -> dict:
    script = (REPO / script_rel).resolve()
    if not script.exists():
        return {"script": script_rel, "status": "MISSING"}

    cmd = [sys.executable, str(script)]
    t0 = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    p = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    t1 = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return {
        "script": script_rel,
        "started_utc": t0,
        "ended_utc": t1,
        "exit_code": p.returncode,
        "stdout_tail": (p.stdout or "").splitlines()[-25:],
        "stderr_tail": (p.stderr or "").splitlines()[-25:],
        "status": "OK" if p.returncode == 0 else "NONZERO",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0, help="start index in COMPARE_ORDER")
    ap.add_argument("--count", type=int, default=-1, help="number of scripts to run (<=0 means all)")
    args = ap.parse_args()

    out_dir = REPO / "out" / "COMPARE_AUDIT"
    out_dir.mkdir(parents=True, exist_ok=True)

    overlay = REPO / "00_TOP" / "OVERLAY"
    if not overlay.exists():
        # Compare needs overlay; write a marker and stop.
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        jp = out_dir / f"compare_suite_run_v0_1_{stamp}.json"
        jp.write_text(
            json.dumps(
                {
                    "version": "v0.1",
                    "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "status": "NO_OVERLAY",
                    "note": "00_TOP/OVERLAY missing; compare suite requires overlay refs.",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"WROTE: {jp}")
        return 1

    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    start = max(0, int(args.start))
    order = COMPARE_ORDER[start:]
    if int(args.count) > 0:
        order = order[: int(args.count)]

    results = []
    for rel in order:
        results.append(_run_one(rel))

    summary = {
        "version": "v0.2",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        # __file__ may be relative depending on how the script is invoked.
        # Resolve to an absolute path before computing a repo-relative runner path.
        "runner": str(Path(__file__).resolve().relative_to(REPO)).replace("\\", "/"),
        "compare_order": COMPARE_ORDER,
        "chunk": {"start": start, "count": int(args.count), "ran": len(order)},
        "results": results,
        "counts": {
            "OK": sum(1 for r in results if r["status"] == "OK"),
            "MISSING": sum(1 for r in results if r["status"] == "MISSING"),
            "NONZERO": sum(1 for r in results if r["status"] == "NONZERO"),
        },
    }

    chunk_tag = f"S{start}_N{len(order)}"
    jp = out_dir / f"compare_suite_run_v0_2_{chunk_tag}_{stamp}.json"
    jp.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Compare suite run (Overlay-only)",
        "",
        f"UTC stamp: {stamp}",
        "",
        "| Script | Status | Exit |",
        "|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['script']} | {r['status']} | {r.get('exit_code')} |")
    mp = out_dir / f"compare_suite_run_v0_2_{chunk_tag}_{stamp}.md"
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"WROTE: {jp}")

    if any(r["status"] == "NONZERO" for r in results):
        return 2
    if any(r["status"] == "MISSING" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
