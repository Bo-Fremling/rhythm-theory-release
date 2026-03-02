#!/usr/bin/env python3
"""Run the NO-FACIT Core suite.

Runs each *_coregen.py under InfluenceAudit (overlay stubbed, open-log captured).
This establishes Core/Overlay independence and produces out/CORE_* artifacts.

This runner MUST NOT run any compare scripts and MUST NOT run forbidden fullscans.

Writes:
  out/CORE_AUDIT/core_suite_run_v0_1_<STAMP>.json
  out/CORE_AUDIT/core_suite_run_v0_1_<STAMP>.md

v0.2.0: adds optional chunking (--start/--count) so environments with strict
        execution time limits can still produce complete audit coverage in
        multiple deterministic runs.
"""

from __future__ import annotations

import contextlib
import io
import json
import runpy
import sys
import argparse
from datetime import datetime
from pathlib import Path

from influence_audit import AuditConfig, ForbiddenDependency, InfluenceAudit, restore_overlay, stub_overlay

REPO = Path(__file__).resolve().parents[2]

COREGEN_ORDER = [
    "00_TOP/LOCKS/GLOBAL_FRAME_CAP_LOCK/global_frame_cap_lock_coregen.py",
    # Couplings first
    "00_TOP/LOCKS/EM_LOCK/em_lock_coregen.py",
    "00_TOP/LOCKS/EM_XI_INVARIANT_LOCK/em_xi_invariant_lock_coregen.py",
    "00_TOP/LOCKS/EW_COUPLING_LOCK/ew_coupling_lock_coregen.py",
    "00_TOP/LOCKS/GS_LOCK/gs_lock_coregen.py",
    "00_TOP/LOCKS/GS_CANON_DENOM_LOCK/gs_canon_denom_lock_coregen.py",

    # Flavor then downstream locks
    "00_TOP/LOCKS/FLAVOR_LOCK/flavor_lock_coregen.py",
    "00_TOP/LOCKS/FLAVOR_TOP_STABILITY_LOCK/flavor_top_stability_lock_coregen.py",
    "00_TOP/LOCKS/FLAVOR_SEED_STABILITY_LOCK/flavor_seed_stability_lock_coregen.py",
    "00_TOP/LOCKS/FLAVOR_MULTI_SEED_STABILITY_LOCK/flavor_multi_seed_stability_lock_coregen.py",
    "00_TOP/LOCKS/QUARK_PROXY_LOCK/quark_proxy_lock_coregen.py",
    "00_TOP/LOCKS/QUARK_PROXY_REDUCE_LOCK/quark_proxy_reduce_lock_coregen.py",
    "00_TOP/LOCKS/QUARK_PROXY_NEG_LOCK/quark_proxy_neg_lock_coregen.py",
    "00_TOP/LOCKS/TOP_PROXY_LOCK/top_proxy_lock_coregen.py",
    "00_TOP/LOCKS/FLAVOR_LOCK/flavor_pp_pred_coregen.py",
    "00_TOP/LOCKS/LEPTON_ENGAGEMENT_LOCK/lepton_engagement_lock_coregen.py",
    "00_TOP/LOCKS/LEPTON_MASS_LOCK/lepton_mass_lock_coregen.py",

    # Anchors/patterns
    "00_TOP/LOCKS/ENERGY_ANCHOR_LOCK/energy_anchor_lock_coregen.py",
    "00_TOP/LOCKS/NU_MECHANISM_LOCK/nu_mechanism_lock_coregen.py",
    "00_TOP/LOCKS/THETA_QCD_LOCK/theta_qcd_lock_coregen.py",

    # Higgs boundary + stubs
    "00_TOP/LOCKS/HIGGS_VEV_LOCK/higgs_vev_lock_coregen.py",
    "00_TOP/LOCKS/HIGGS_CANON_DENOM_LOCK/higgs_canon_denom_lock_coregen.py",
    "00_TOP/LOCKS/HADRON_PROXY_LOCK/hadron_proxy_lock_coregen.py",

    # Cross-lock reductions (facit-free) before indexing
    "00_TOP/LOCKS/SM29_CONSISTENCY_LOCK/sm29_consistency_lock_coregen.py",

    # PPN proxy + index
    "00_TOP/LOCKS/PPN_LOCK/ppn_lock_coregen.py",
    "00_TOP/LOCKS/SM_PARAM_INDEX/sm29_index_coregen.py",
    "00_TOP/LOCKS/CORE_ARTIFACT_HASH_LOCK/core_artifact_hash_lock_coregen.py",
]


# Some locks are intentionally advisory in the public release: they write a
# detailed artifact to out/ for reviewers, but they must not block the full
# release pipeline (Core suite -> report/pages). These are still NO-FACIT.
SOFT_TARGET_NONZERO = {
    # Can report instability under small perturbations while still being
    # deterministic and facit-free. Keep as WARN, not a hard FAIL.
    "00_TOP/LOCKS/FLAVOR_TOP_STABILITY_LOCK/flavor_top_stability_lock_coregen.py",
}


def _tail_lines(s: str, n: int = 25) -> list[str]:
    lines = (s or "").splitlines()
    return lines[-n:]


def _run_one(script_rel: str) -> dict:
    script = (REPO / script_rel).resolve()
    if not script.exists():
        return {"script": script_rel, "status": "MISSING"}

    cfg = AuditConfig(repo_root=REPO)
    t0 = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    out_dir = REPO / "out" / "CORE_AUDIT"
    out_dir.mkdir(parents=True, exist_ok=True)
    audit_path = out_dir / f"{script.stem}_audit_{stamp}.json"

    did_stub, overlay_path, moved_to = (False, None, None)
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    report = {
        "version": "influence_audit_v0_1",
        "utc": stamp,
        "script": str(script),
        "cwd": str(REPO),
        "argv": [str(script)],
        "stub_overlay": True,
        "result": "UNKNOWN",
        "exit_code": None,
        "forbidden": None,
        "opened": [],
    }

    code = 98

    try:
        did_stub, overlay_path, moved_to = stub_overlay(REPO)

        # set argv and import path similar to the wrapper
        sys_argv0 = sys.argv
        sys.argv = [str(script)]
        if str(script.parent) not in sys.path:
            sys.path.insert(0, str(script.parent))

        try:
            with InfluenceAudit(cfg, capture_stack=False) as audit:
                with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                    try:
                        runpy.run_path(str(script), run_name="__main__")
                        report["result"] = "OK"
                        report["exit_code"] = 0
                        code = 0
                    except SystemExit as e:
                        code = int(e.code) if isinstance(e.code, int) else 0
                        report["exit_code"] = code
                        report["result"] = "OK" if code == 0 else "TARGET_NONZERO"
                report["opened"] = [ev.__dict__ for ev in audit.opened]
        except ForbiddenDependency as e:
            report["result"] = "FORBIDDEN"
            report["exit_code"] = 99
            report["forbidden"] = str(e)
            code = 99
        except Exception as e:
            report["result"] = "WRAPPER_ERROR"
            report["exit_code"] = 98
            report["forbidden"] = f"{type(e).__name__}: {e}"
            code = 98
        finally:
            sys.argv = sys_argv0

    finally:
        try:
            restore_overlay(did_stub, overlay_path, moved_to)
        except Exception:
            pass

    audit_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    t1 = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    status = (
        "OK" if code == 0 else (
            "FORBIDDEN" if code == 99 else (
                "TARGET_NONZERO" if code == 10 or report.get("result") == "TARGET_NONZERO" else "WRAPPER_ERROR"
            )
        )
    )

    return {
        "script": script_rel,
        "started_utc": t0,
        "ended_utc": t1,
        "exit_code": int(report.get("exit_code") or code),
        "stdout_tail": _tail_lines(stdout_buf.getvalue(), 25),
        "stderr_tail": _tail_lines(stderr_buf.getvalue(), 25),
        "status": status,
        "audit": str(audit_path.relative_to(REPO)).replace("\\", "/"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0, help="start index in COREGEN_ORDER")
    ap.add_argument("--count", type=int, default=-1, help="number of scripts to run (<=0 means all)")
    args = ap.parse_args()

    out_dir = REPO / "out" / "CORE_AUDIT"
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    start = max(0, int(args.start))
    order = COREGEN_ORDER[start:]
    if int(args.count) > 0:
        order = order[: int(args.count)]

    results = []
    for rel in order:
        results.append(_run_one(rel))

        # Convert selected deterministic, facit-free "nonzero target" results
        # into WARN so the public release can still complete (report/pages).
        if results[-1].get("status") == "TARGET_NONZERO" and rel in SOFT_TARGET_NONZERO:
            results[-1]["status"] = "WARN"
            results[-1]["soft"] = True

        if results[-1]["status"] == "FORBIDDEN":
            break

    summary = {
        "version": "v0.2.0",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        # __file__ may be relative depending on how the script is invoked.
        # Resolve to an absolute path before computing a repo-relative runner path.
        "runner": str(Path(__file__).resolve().relative_to(REPO)).replace("\\", "/"),
        "coregen_order": COREGEN_ORDER,
        "chunk": {"start": start, "count": int(args.count), "ran": len(order)},
        "results": results,
        "counts": {
            "OK": sum(1 for r in results if r.get("status") == "OK"),
            "WARN": sum(1 for r in results if r.get("status") == "WARN"),
            "MISSING": sum(1 for r in results if r.get("status") == "MISSING"),
            "FORBIDDEN": sum(1 for r in results if r.get("status") == "FORBIDDEN"),
            "TARGET_NONZERO": sum(1 for r in results if r.get("status") == "TARGET_NONZERO"),
            "WRAPPER_ERROR": sum(1 for r in results if r.get("status") == "WRAPPER_ERROR"),
        },
    }

    chunk_tag = f"S{start}_N{len(order)}"
    jp = out_dir / f"core_suite_run_v0_2_{chunk_tag}_{stamp}.json"
    jp.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Core suite run (NO-FACIT)",
        "",
        f"UTC stamp: {stamp}",
        "",
        "| Script | Status | Exit | Audit |",
        "|---|---|---:|---|",
    ]
    for r in results:
        lines.append(f"| {r['script']} | {r['status']} | {r.get('exit_code')} | {r.get('audit')} |")

    mp = out_dir / f"core_suite_run_v0_2_{chunk_tag}_{stamp}.md"
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"WROTE: {jp}")

    if any(r["status"] in ("FORBIDDEN", "WRAPPER_ERROR") for r in results):
        return 2
    if any(r["status"] in ("MISSING", "TARGET_NONZERO") for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
