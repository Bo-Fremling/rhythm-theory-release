#!/usr/bin/env python3
"""
verify_all.py (Python-first verifier for RT Release)

Goal:
- Run the same verification pipeline as verify/verify_all.sh, but without bash.
- Cross-platform: works on Windows/macOS/Linux with Python 3.8+.

What it does (default):
1) Core verification (NO-FACIT): static grep + core suite (chunked) + merge + NEG checks + audit-scope check.
2) Compare verification: compare suite (chunked) + merge.
3) SM29 match triage + report/pages generation.

Exit codes:
0 = PASS
nonzero = FAIL (mirrors the bash pipeline: compare/match failures propagate)

Notes:
- Requires project runtime deps as needed by the suite (see requirements.txt).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def _root() -> Path:
    return Path(__file__).resolve().parent


def _default_env() -> Dict[str, str]:
    """
    Environment knobs to reduce drift across machines.
    Mirrors verify/*.sh defaults but is passed to child processes.
    """
    env = dict(os.environ)

    env.setdefault("TZ", "UTC")
    env.setdefault("PYTHONHASHSEED", "0")
    env.setdefault("LC_ALL", "C.UTF-8")
    env.setdefault("LANG", "C.UTF-8")

    # Threading determinism (numpy/blas)
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("MKL_NUM_THREADS", "1")
    env.setdefault("OPENBLAS_NUM_THREADS", "1")
    env.setdefault("NUMEXPR_NUM_THREADS", "1")
    return env


def _run_stream(cmd: List[str], cwd: Path, env: Dict[str, str]) -> Tuple[int, str]:
    """
    Run a command, stream combined stdout+stderr to the console, and also capture it.
    Returns (returncode, full_output_text).
    """
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    assert proc.stdout is not None
    out_lines: List[str] = []
    for line in proc.stdout:
        out_lines.append(line)
        # Mirror bash behavior: log to stderr for reviewer visibility.
        sys.stderr.write(line)
    proc.wait()
    return int(proc.returncode or 0), "".join(out_lines)


_WROTE_RE = re.compile(r"^WROTE:\s*(.+?)\s*$", re.MULTILINE)


def _parse_wrote_path(output: str) -> Optional[str]:
    m = None
    for mm in _WROTE_RE.finditer(output or ""):
        m = mm
    return m.group(1) if m else None


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _import_order_len(which: str, tools_dir: Path) -> int:
    """
    Read COREGEN_ORDER / COMPARE_ORDER lengths without spawning extra processes.
    """
    sys.path.insert(0, str(tools_dir))
    try:
        if which == "core":
            import run_core_no_facit_suite as m  # type: ignore
            order = getattr(m, "COREGEN_ORDER", []) or []
        else:
            import run_compare_suite as m  # type: ignore
            order = getattr(m, "COMPARE_ORDER", []) or []
        return int(len(order))
    finally:
        try:
            sys.path.remove(str(tools_dir))
        except ValueError:
            pass


def _clean_out(root: Path) -> None:
    out = root / "out"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)


def _core_neg_tests(root: Path) -> None:
    # Import InfluenceAudit stack
    tools = root / "00_TOP" / "TOOLS"
    sys.path.insert(0, str(tools))
    try:
        from influence_audit import AuditConfig, InfluenceAudit, ForbiddenDependency  # type: ignore
    finally:
        sys.path.pop(0)

    repo = root.resolve()
    cfg = AuditConfig(repo_root=repo)

    overlay_dir = repo / "00_TOP" / "OVERLAY"

    # NEG 1: out-of-repo bait (copy one overlay file to temp path)
    if overlay_dir.exists():
        sample_files = sorted([p for p in overlay_dir.rglob("*") if p.is_file()])
        if sample_files:
            sample = sample_files[0]
            fd, tmp_path = tempfile.mkstemp(prefix="rt_overlay_sample_", suffix=".bin")
            os.close(fd)
            try:
                try:
                    shutil.copyfile(sample, tmp_path)
                except Exception:
                    # If copy fails, still test that open is forbidden.
                    pass
                target = Path(tmp_path).resolve()
                sys.stderr.write(f"[core] NEG: audit must forbid reading out-of-repo bait: {target}\n")
                try:
                    with InfluenceAudit(cfg, capture_stack=False):
                        Path(target).open("rb").read(1)
                except ForbiddenDependency:
                    print("[core] NEG: PASS (forbidden as expected)")
                except Exception as e:
                    raise SystemExit(f"[core] NEG: unexpected exception: {e!r}")
                else:
                    raise SystemExit("[core] NEG: FAIL (out-of-repo read was allowed)")
            finally:
                try:
                    Path(tmp_path).unlink()
                except Exception:
                    pass

    # NEG 2: in-repo OVERLAY open must be forbidden
    if overlay_dir.exists():
        sample_files = sorted([p for p in overlay_dir.rglob("*") if p.is_file()])
        if sample_files:
            target = sample_files[0].resolve()
            sys.stderr.write(f"[core] NEG: audit must forbid opening in-repo OVERLAY file: {target}\n")
            try:
                with InfluenceAudit(cfg, capture_stack=False):
                    Path(target).open("rb").read(1)
            except ForbiddenDependency:
                print("[core] NEG: PASS (OVERLAY forbidden as expected)")
            except Exception as e:
                raise SystemExit(f"[core] NEG: unexpected exception: {e!r}")
            else:
                raise SystemExit("[core] NEG: FAIL (OVERLAY read was allowed)")

    # NEG 3: *reference*.json must be forbidden even under allowed roots
    neg_ref = repo / "out" / "tmp_reference_test_reference.json"
    neg_ref.parent.mkdir(parents=True, exist_ok=True)
    neg_ref.write_text('{"note":"neg test"}\n', encoding="utf-8")
    sys.stderr.write(f"[core] NEG: audit must forbid opening glob-matching reference file: {neg_ref}\n")
    try:
        try:
            with InfluenceAudit(cfg, capture_stack=False):
                neg_ref.open("rb").read(1)
        except ForbiddenDependency:
            print("[core] NEG: PASS (*reference*.json forbidden as expected)")
        except Exception as e:
            raise SystemExit(f"[core] NEG: unexpected exception: {e!r}")
        else:
            raise SystemExit("[core] NEG: FAIL (*reference*.json read was allowed)")
    finally:
        try:
            neg_ref.unlink()
        except Exception:
            pass


def _run_core_suite(root: Path, env: Dict[str, str], chunk_size: int, label: str = "baseline") -> Path:
    tools_dir = root / "00_TOP" / "TOOLS"
    n_total = _import_order_len("core", tools_dir)
    if n_total <= 0:
        raise SystemExit("FAIL: could not determine COREGEN_ORDER length")

    sys.stderr.write(f"[core] run suite ({label}) [chunked size={chunk_size}]\n")

    chunk_paths: List[Path] = []
    start = 0
    while start < n_total:
        size = int(chunk_size)
        while True:
            cmd = [sys.executable, "-u", str(root / "00_TOP" / "TOOLS" / "run_core_no_facit_suite.py"),
                   "--start", str(start), "--count", str(size)]
            rc, out = _run_stream(cmd, cwd=root, env=env)
            wrote = _parse_wrote_path(out)
            outp = None
            if wrote:
                wp = Path(wrote)
                outp = (wp if wp.is_absolute() else (root / wp)).resolve()
            if wrote and outp is not None and outp.is_file() and rc == 0:
                chunk_paths.append(outp)
                break

            if size <= 1:
                raise SystemExit(f"FAIL: core suite chunk failed repeatedly at start={start} (rc={rc})")
            size = (size + 1) // 2
            sys.stderr.write(f"[core] retry chunk start={start} with smaller count={size}\n")

        obj = _load_json(chunk_paths[-1])
        ran = int(((obj.get("chunk") or {}).get("ran") or 0))
        if ran <= 0:
            raise SystemExit(f"FAIL: could not read chunk.ran from {chunk_paths[-1]}")
        start += ran

    # Merge
    merge = root / "verify" / "merge_core_suite_chunks.py"
    cmd = [sys.executable, "-u", str(merge), "--label", label] + [str(p) for p in chunk_paths]
    rc, _ = _run_stream(cmd, cwd=root, env=env)
    if rc != 0:
        raise SystemExit(f"FAIL: merge_core_suite_chunks failed (rc={rc})")

    # Find latest merged FULL report
    aud = root / "out" / "CORE_AUDIT"
    files = sorted(aud.glob(f"core_suite_run_v0_2_FULL_{label}_*.json"))
    if not files:
        raise SystemExit(f"FAIL: missing merged FULL core suite report for {label}")
    return files[-1]


def _run_compare_suite(root: Path, env: Dict[str, str], chunk_size: int) -> Path:
    tools_dir = root / "00_TOP" / "TOOLS"
    n_total = _import_order_len("compare", tools_dir)
    if n_total <= 0:
        raise SystemExit("FAIL: could not determine COMPARE_ORDER length")

    sys.stderr.write(f"[compare] run suite [chunked size={chunk_size}]\n")

    chunk_paths: List[Path] = []
    start = 0
    while start < n_total:
        size = int(chunk_size)
        while True:
            cmd = [sys.executable, "-u", str(root / "00_TOP" / "TOOLS" / "run_compare_suite.py"),
                   "--start", str(start), "--count", str(size)]
            rc, out = _run_stream(cmd, cwd=root, env=env)
            wrote = _parse_wrote_path(out)
            outp = None
            if wrote:
                wp = Path(wrote)
                outp = (wp if wp.is_absolute() else (root / wp)).resolve()
            if wrote and outp is not None and outp.is_file() and rc == 0:
                chunk_paths.append(outp)
                break

            if size <= 1:
                raise SystemExit(f"FAIL: compare suite chunk failed repeatedly at start={start} (rc={rc})")
            size = (size + 1) // 2
            sys.stderr.write(f"[compare] retry chunk start={start} with smaller count={size}\n")

        obj = _load_json(chunk_paths[-1])
        ran = int(((obj.get("chunk") or {}).get("ran") or 0))
        if ran <= 0:
            raise SystemExit(f"FAIL: could not read chunk.ran from {chunk_paths[-1]}")
        start += ran

    # Merge
    merge = root / "verify" / "merge_compare_suite_chunks.py"
    cmd = [sys.executable, "-u", str(merge)] + [str(p) for p in chunk_paths]
    rc, _ = _run_stream(cmd, cwd=root, env=env)
    if rc != 0:
        raise SystemExit(f"FAIL: merge_compare_suite_chunks failed (rc={rc})")

    # Find latest merged FULL report
    aud = root / "out" / "COMPARE_AUDIT"
    files = sorted(aud.glob("compare_suite_run_v0_2_FULL_*.json"))
    if not files:
        raise SystemExit("FAIL: no merged FULL compare_suite_run json found")
    return files[-1]


def _summarize_core(root: Path, full_report: Path) -> None:
    obj = _load_json(full_report)
    counts = obj.get("counts") or {}
    for key in ("FORBIDDEN", "MISSING", "TARGET_NONZERO", "WRAPPER_ERROR"):
        if int(counts.get(key, 0)) != 0:
            raise SystemExit(f"FAIL: {key}={counts.get(key)} in {full_report.name}")

    idx_dir = root / "out" / "CORE_SM29_INDEX"
    idx_files = sorted(idx_dir.glob("sm29_core_index_v*.json"))
    idx_latest = idx_files[-1] if idx_files else None

    status_counts: Dict[str, int] = {}
    if idx_latest and idx_latest.exists():
        data = _load_json(idx_latest)
        for e in data.get("entries", []):
            s = e.get("derivation_status", "UNKNOWN")
            status_counts[s] = status_counts.get(s, 0) + 1

    print(f"CORE_VERIFY: PASS ({full_report.name})")
    print("\n[core] where to look:")
    print(f"- audit:   out/CORE_AUDIT/{full_report.name}")
    if idx_latest:
        md = idx_latest.with_suffix(".md")
        print(f"- index:   {idx_latest.as_posix()}")
        if md.exists():
            print(f"- indexmd: {md.as_posix()}")
        if status_counts:
            keys = ["DERIVED", "CANDIDATE-SET", "HYP", "BLANK", "UNKNOWN"]
            sline = ", ".join([f"{k}={status_counts.get(k,0)}" for k in keys if status_counts.get(k, 0)])
            if sline:
                print(f"- counts:  {sline}")
    else:
        print("- index:   out/CORE_SM29_INDEX/(missing)")


def _summarize_compare(root: Path, full_report: Path) -> None:
    obj = _load_json(full_report)
    counts = obj.get("counts") or {}
    for key in ("MISSING", "NONZERO"):
        if int(counts.get(key, 0)) != 0:
            raise SystemExit(f"FAIL: {key}={counts.get(key)} in {full_report.name}")

    idx_dir = root / "out" / "COMPARE_SM29_INDEX"
    idx_files = sorted(idx_dir.glob("sm29_compare_index_v*.json"))
    idx_latest = idx_files[-1] if idx_files else None

    status_counts: Dict[str, int] = {}
    if idx_latest and idx_latest.exists():
        data = _load_json(idx_latest)
        for e in data.get("entries", []):
            s = e.get("validation_status", "UNKNOWN")
            status_counts[s] = status_counts.get(s, 0) + 1

    print(f"COMPARE_VERIFY: PASS ({full_report.name})")
    print("\n[compare] where to look:")
    print(f"- audit:   out/COMPARE_AUDIT/{full_report.name}")
    if idx_latest:
        md = idx_latest.with_suffix(".md")
        print(f"- index:   {idx_latest.as_posix()}")
        if md.exists():
            print(f"- indexmd: {md.as_posix()}")
        if status_counts:
            keys = ["AGREES", "TENSION", "COMPARED", "UNTESTED", "UNKNOWN"]
            sline = ", ".join([f"{k}={status_counts.get(k,0)}" for k in keys if status_counts.get(k, 0)])
            if sline:
                print(f"- counts:  {sline}")
    else:
        print("- index:   out/COMPARE_SM29_INDEX/(missing)")


def _overlay_off_test(root: Path, env: Dict[str, str], chunk_size: int) -> Optional[Path]:
    """
    Optional strict mode: run a second full core suite in a temp workcopy with OVERLAY removed.
    Enabled by CORE_OVERLAY_OFF=1.
    """
    if os.environ.get("CORE_OVERLAY_OFF", "0") != "1":
        sys.stderr.write("[core] overlay-off test: SKIP (set CORE_OVERLAY_OFF=1 to enable)\n")
        return None

    label = "overlay_off"
    tmp_repo = Path(tempfile.mkdtemp(prefix=f"rt_verify_core_{label}_"))
    sys.stderr.write(f"[core] {label}: create temp workcopy: {tmp_repo}\n")

    try:
        ignore = shutil.ignore_patterns("out", "__pycache__", "*.pyc", "*.pyo", ".git", ".venv", "venv")
        shutil.copytree(root, tmp_repo, dirs_exist_ok=True, ignore=ignore)

        ov = tmp_repo / "00_TOP" / "OVERLAY"
        if ov.exists():
            shutil.rmtree(ov)
        for p in tmp_repo.rglob("*reference*.json"):
            try:
                p.unlink()
            except Exception:
                pass

        time.sleep(1)

        full = _run_core_suite(tmp_repo, env, chunk_size, label=label)

        # Copy audit artifacts back for reviewer visibility
        (root / "out" / "CORE_AUDIT").mkdir(parents=True, exist_ok=True)
        src_aud = tmp_repo / "out" / "CORE_AUDIT"
        if src_aud.exists():
            for p in src_aud.glob("*"):
                try:
                    shutil.copy2(p, root / "out" / "CORE_AUDIT" / p.name)
                except Exception:
                    pass

        # Compare semhash with baseline
        aud = root / "out" / "CORE_AUDIT"
        bfiles = sorted(aud.glob("core_suite_run_v0_2_FULL_baseline_*.json"))
        ofiles = sorted(aud.glob("core_suite_run_v0_2_FULL_overlay_off_*.json"))
        if not bfiles or not ofiles:
            raise SystemExit("FAIL: missing merged FULL reports for baseline or overlay_off")
        b = _load_json(bfiles[-1])
        o = _load_json(ofiles[-1])
        hb = ((b.get("combined") or {}).get("semhash"))
        ho = ((o.get("combined") or {}).get("semhash"))
        if not hb or not ho:
            raise SystemExit("FAIL: missing combined semhash in FULL report(s)")
        if hb != ho:
            raise SystemExit(f"FAIL: suite semhash mismatch baseline vs overlay_off: {hb} != {ho}")
        print(f"[core] suite semhash stable across overlay_off: {hb}")
        return full
    finally:
        try:
            shutil.rmtree(tmp_repo)
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--core-only", action="store_true", help="run only core verification")
    ap.add_argument("--compare-only", action="store_true", help="run only compare verification")
    ap.add_argument("--skip-compare", action="store_true", help="skip compare verification")
    ap.add_argument("--skip-match", action="store_true", help="skip sm29_data_match.py")
    ap.add_argument("--skip-report", action="store_true", help="skip sm29_report.py")
    ap.add_argument("--core-chunk", type=int, default=int(os.environ.get("CORE_SUITE_CHUNK_SIZE", "6")))
    ap.add_argument("--compare-chunk", type=int, default=int(os.environ.get("COMPARE_SUITE_CHUNK_SIZE", "4")))
    args = ap.parse_args()

    root = _root()
    env = _default_env()

    # Core / Compare flags sanity
    if args.core_only and args.compare_only:
        raise SystemExit("Choose at most one of --core-only / --compare-only")

    if not (root / "00_TOP" / "TOOLS").exists():
        raise SystemExit("FAIL: this script must be placed in the Release repo root (next to 00_TOP/)")

    # Core verify
    core_rc = 0
    compare_rc = 0
    match_rc = 0

    if not args.compare_only:
        # Defense-in-depth: static grep for bypass modules in *_coregen.py
        rc, _ = _run_stream([sys.executable, "-u", str(root / "verify" / "static_core_safety_grep.py")], cwd=root, env=env)
        if rc != 0:
            raise SystemExit(f"FAIL: static_core_safety_grep failed (rc={rc})")

        sys.stderr.write("[core] clean out/\n")
        _clean_out(root)

        full_core = _run_core_suite(root, env, int(args.core_chunk), label="baseline")

        # NEG controls
        _core_neg_tests(root)

        # Optional overlay-off mode
        _overlay_off_test(root, env, int(args.core_chunk))

        # Defense-in-depth: audit open scopes
        rc, _ = _run_stream([sys.executable, "-u", str(root / "verify" / "check_audit_open_scopes.py")], cwd=root, env=env)
        if rc != 0:
            raise SystemExit(f"FAIL: check_audit_open_scopes failed (rc={rc})")

        _summarize_core(root, full_core)

        if args.core_only:
            return 0

    # Compare verify
    if not args.core_only and not args.skip_compare:
        try:
            full_cmp = _run_compare_suite(root, env, int(args.compare_chunk))
            _summarize_compare(root, full_cmp)
        except SystemExit as e:
            # Keep behavior like bash: compare failure is recorded, pipeline continues to report/match.
            compare_rc = int(e.code) if isinstance(e.code, int) else 2

    if args.compare_only:
        return 0 if compare_rc == 0 else compare_rc

    # Match triage + report
    if not args.skip_match:
        sys.stderr.write("[match] generate SM29 data-match (overlay triage)\n")
        rc, _ = _run_stream([sys.executable, "-u", str(root / "00_TOP" / "LOCKS" / "SM_PARAM_INDEX" / "sm29_data_match.py")], cwd=root, env=env)
        match_rc = int(rc)
        if match_rc != 0:
            sys.stderr.write(f"[match] FAILED (exit={match_rc}) — see out/SM_PARAM_INDEX/\n")

    if not args.skip_report:
        sys.stderr.write("[report] generate SM29 report + pages\n")
        rc, _ = _run_stream([sys.executable, "-u", str(root / "00_TOP" / "LOCKS" / "SM_PARAM_INDEX" / "sm29_report.py")], cwd=root, env=env)
        if rc != 0:
            raise SystemExit(f"FAIL: sm29_report.py failed (rc={rc})")

    if compare_rc != 0:
        print(f"ALL_VERIFY: FAIL (compare exit={compare_rc})")
        return int(compare_rc)
    if match_rc != 0:
        print(f"ALL_VERIFY: FAIL (sm29_data_match exit={match_rc})")
        return int(match_rc)

    print("ALL_VERIFY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
