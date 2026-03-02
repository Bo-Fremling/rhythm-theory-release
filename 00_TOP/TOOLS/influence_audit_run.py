#!/usr/bin/env python3
"""Run a python script under InfluenceAudit.

Default behavior:
- Stub overlay directory (rename 00_TOP/OVERLAY -> OVERLAY__STUBBED__DO_NOT_USE)
- Log all opened files
- HARD FAIL if forbidden paths are opened

Outputs:
- out/CORE_AUDIT/<script_basename>_audit.json

Exit codes:
- 0: target exited 0 and no forbidden dependency
- 10: target exited nonzero (but no forbidden dependency)
- 99: forbidden dependency detected
- 98: wrapper error
"""

from __future__ import annotations

import argparse
import json
import runpy
import sys
from datetime import datetime
from pathlib import Path

from influence_audit import AuditConfig, ForbiddenDependency, InfluenceAudit, restore_overlay, stub_overlay


def _repo_root_from_here(here: Path) -> Path:
    # .../00_TOP/TOOLS/influence_audit_run.py
    return here.resolve().parents[2]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("script", help="Path to target script (usually *_coregen.py)")
    ap.add_argument("--no-stub-overlay", action="store_true", help="Do not stub 00_TOP/OVERLAY during run")
    ap.add_argument("--capture-stack", action="store_true", help="Capture small stack trace per open event")
    ap.add_argument("script_args", nargs=argparse.REMAINDER, help="Args after -- are passed to target")
    args = ap.parse_args()

    here = Path(__file__).resolve()
    repo = _repo_root_from_here(here)

    script = Path(args.script)
    if not script.is_absolute():
        script = (Path.cwd() / script).resolve()

    out_dir = repo / "out" / "CORE_AUDIT"
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    report_path = out_dir / f"{script.stem}_audit_{stamp}.json"

    did_stub, overlay_path, moved_to = (False, None, None)

    cfg = AuditConfig(repo_root=repo)

    report = {
        "version": "influence_audit_v0_1",
        "utc": stamp,
        "script": str(script),
        "cwd": str(Path.cwd()),
        "argv": [args.script] + (args.script_args or []),
        "stub_overlay": (not args.no_stub_overlay),
        "result": "UNKNOWN",
        "exit_code": None,
        "forbidden": None,
        "opened": [],
    }

    try:
        if not args.no_stub_overlay:
            did_stub, overlay_path, moved_to = stub_overlay(repo)

        # set sys.argv for target
        sys_argv0 = sys.argv
        sys.argv = [str(script)] + (args.script_args or [])
        # ensure target directory is importable
        if str(script.parent) not in sys.path:
            sys.path.insert(0, str(script.parent))

        try:
            with InfluenceAudit(cfg, capture_stack=args.capture_stack) as audit:
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
            # do not mask earlier failures
            pass

    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {report_path}")

    if report["result"] == "OK" and report["exit_code"] == 0:
        return 0
    if report["result"] == "FORBIDDEN":
        return 99
    if report["result"] == "TARGET_NONZERO":
        return 10
    return 98


if __name__ == "__main__":
    raise SystemExit(main())
