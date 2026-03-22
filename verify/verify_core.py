from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from verify.verify_py_common import (
    ROOT,
    apply_determinism_env,
    copytree_release,
    latest_file,
    merge_json_args,
    module_len,
    parse_wrote,
    read_chunk_ran,
    run_cmd,
    python_cmd,
    remove_overlay_and_references,
)


def run_one_chunk(start: int, count: int, cwd: Path, env: dict) -> tuple[Path | None, int]:
    cp = run_cmd(
        python_cmd('00_TOP/TOOLS/run_core_no_facit_suite.py', '--start', str(start), '--count', str(count)),
        cwd=cwd,
        env=env,
        check=False,
    )
    wrote = parse_wrote(cp.stdout + ('\n' + cp.stderr if cp.stderr else ''))
    return wrote, cp.returncode


def run_suite_chunked(label: str, cwd: Path, env: dict, chunk_size: int) -> None:
    print(f'[core] run suite ({label}) [chunked size={chunk_size}]')
    n_total = module_len('run_core_no_facit_suite', 'COREGEN_ORDER', cwd=cwd, env=env)
    chunk_paths: list[str] = []
    start = 0
    while start < n_total:
        size = chunk_size
        while True:
            outp, rc = run_one_chunk(start, size, cwd, env)
            if outp is not None and outp.exists() and rc == 0:
                break
            if size <= 1:
                raise SystemExit(f'FAIL: core suite chunk failed repeatedly at start={start} (rc={rc})')
            size = (size + 1) // 2
            print(f'[core] retry chunk start={start} with smaller count={size}', file=sys.stderr)
        chunk_paths.append(str(outp))
        ran = read_chunk_ran(outp)
        if ran <= 0:
            raise SystemExit(f'FAIL: could not read chunk.ran from {outp}')
        start += ran
    merge_json_args('verify/merge_core_suite_chunks.py', ['--label', label, *chunk_paths], cwd=cwd, env=env)


def run_suite_chunked_in_temp_repo(label: str, env: dict, chunk_size: int) -> None:
    tmp_repo = Path(tempfile.mkdtemp(prefix=f'rt_verify_core_{label}_'))
    print(f'[core] {label}: create temp workcopy: {tmp_repo}', file=sys.stderr)
    copytree_release(ROOT, tmp_repo)
    remove_overlay_and_references(tmp_repo)
    time.sleep(1)
    run_suite_chunked(label, tmp_repo, env, chunk_size)
    (ROOT / 'out' / 'CORE_AUDIT').mkdir(parents=True, exist_ok=True)
    src = tmp_repo / 'out' / 'CORE_AUDIT'
    if src.exists():
        for item in src.iterdir():
            dst = ROOT / 'out' / 'CORE_AUDIT' / item.name
            if item.is_file():
                shutil.copy2(item, dst)
    shutil.rmtree(tmp_repo, ignore_errors=True)


def neg_out_of_repo(env: dict) -> None:
    overlay_dir = ROOT / '00_TOP' / 'OVERLAY'
    if not overlay_dir.exists():
        return
    sample = next((p for p in overlay_dir.rglob('*') if p.is_file()), None)
    if sample is None:
        return
    fd, tmp_name = tempfile.mkstemp(prefix='rt_overlay_sample.')
    os.close(fd)
    tmp_path = Path(tmp_name)
    shutil.copy2(sample, tmp_path)
    print(f'[core] NEG: audit must forbid reading out-of-repo bait: {tmp_path}', file=sys.stderr)
    code = f"""
from pathlib import Path
import sys
sys.path.insert(0, '00_TOP/TOOLS')
from influence_audit import AuditConfig, InfluenceAudit, ForbiddenDependency
root = Path('.').resolve()
cfg = AuditConfig(repo_root=root)
target = Path(r'''{tmp_path}''').resolve()
try:
    with InfluenceAudit(cfg, capture_stack=False):
        Path(target).open('rb').read(1)
except ForbiddenDependency:
    print('[core] NEG: PASS (forbidden as expected)')
    raise SystemExit(0)
except Exception as e:
    print('[core] NEG: unexpected exception:', repr(e))
    raise SystemExit(2)
print('[core] NEG: FAIL (out-of-repo read was allowed)')
raise SystemExit(1)
"""
    try:
        run_cmd(python_cmd('-c', code), env=env)
    finally:
        tmp_path.unlink(missing_ok=True)


def neg_in_repo_overlay(env: dict) -> None:
    overlay_dir = ROOT / '00_TOP' / 'OVERLAY'
    if not overlay_dir.exists():
        return
    sample = next((p for p in overlay_dir.rglob('*') if p.is_file()), None)
    if sample is None:
        return
    print(f'[core] NEG: audit must forbid opening in-repo OVERLAY file: {sample}', file=sys.stderr)
    code = f"""
from pathlib import Path
import sys
sys.path.insert(0, '00_TOP/TOOLS')
from influence_audit import AuditConfig, InfluenceAudit, ForbiddenDependency
root = Path('.').resolve()
cfg = AuditConfig(repo_root=root)
target = (root / Path(r'''{sample.relative_to(ROOT)}''')).resolve()
try:
    with InfluenceAudit(cfg, capture_stack=False):
        Path(target).open('rb').read(1)
except ForbiddenDependency:
    print('[core] NEG: PASS (OVERLAY forbidden as expected)')
    raise SystemExit(0)
except Exception as e:
    print('[core] NEG: unexpected exception:', repr(e))
    raise SystemExit(2)
print('[core] NEG: FAIL (OVERLAY read was allowed)')
raise SystemExit(1)
"""
    run_cmd(python_cmd('-c', code), env=env)


def neg_reference_glob(env: dict) -> None:
    neg_ref = ROOT / 'out' / 'tmp_reference_test_reference.json'
    neg_ref.parent.mkdir(parents=True, exist_ok=True)
    neg_ref.write_text('{"note":"neg test"}\n', encoding='utf-8')
    print(f'[core] NEG: audit must forbid opening glob-matching reference file: {neg_ref.relative_to(ROOT)}', file=sys.stderr)
    code = """
from pathlib import Path
import sys
sys.path.insert(0, '00_TOP/TOOLS')
from influence_audit import AuditConfig, InfluenceAudit, ForbiddenDependency
root = Path('.').resolve()
cfg = AuditConfig(repo_root=root)
target = (root / Path('out/tmp_reference_test_reference.json')).resolve()
try:
    with InfluenceAudit(cfg, capture_stack=False):
        Path(target).open('rb').read(1)
except ForbiddenDependency:
    print('[core] NEG: PASS (*reference*.json forbidden as expected)')
    raise SystemExit(0)
except Exception as e:
    print('[core] NEG: unexpected exception:', repr(e))
    raise SystemExit(2)
print('[core] NEG: FAIL (*reference*.json read was allowed)')
raise SystemExit(1)
"""
    try:
        run_cmd(python_cmd('-c', code), env=env)
    finally:
        neg_ref.unlink(missing_ok=True)


def final_summary() -> None:
    aud = ROOT / 'out' / 'CORE_AUDIT'
    files = sorted(aud.glob('core_suite_run_v0_2_FULL_overlay_off_*.json'))
    if not files:
        files = sorted(aud.glob('core_suite_run_v0_2_FULL_baseline_*.json'))
    if not files:
        raise SystemExit('FAIL: no merged FULL core suite report found (overlay_off or baseline)')
    latest = files[-1]
    obj = json.loads(latest.read_text(encoding='utf-8'))
    counts = obj.get('counts') or {}
    for key in ('FORBIDDEN', 'MISSING', 'TARGET_NONZERO', 'WRAPPER_ERROR'):
        if int(counts.get(key, 0)) != 0:
            raise SystemExit(f'FAIL: {key}={counts.get(key)} in {latest.name}')
    idx_dir = ROOT / 'out' / 'CORE_SM29_INDEX'
    idx_files = sorted(idx_dir.glob('sm29_core_index_v*.json'))
    idx_latest = idx_files[-1] if idx_files else None
    status_counts: dict[str, int] = {}
    if idx_latest:
        data = json.loads(idx_latest.read_text(encoding='utf-8'))
        for e in data.get('entries', []):
            s = e.get('derivation_status', 'UNKNOWN')
            status_counts[s] = status_counts.get(s, 0) + 1
    print(f'CORE_VERIFY: PASS ({latest.name})')
    print('\n[core] where to look:')
    print(f'- audit:   out/CORE_AUDIT/{latest.name}')
    if idx_latest:
        md = idx_latest.with_suffix('.md')
        print(f'- index:   {idx_latest.as_posix()}')
        if md.exists():
            print(f'- indexmd: {md.as_posix()}')
        keys = ['DERIVED', 'CANDIDATE-SET', 'HYP', 'BLANK', 'UNKNOWN']
        sline = ', '.join([f'{k}={status_counts.get(k,0)}' for k in keys if status_counts.get(k,0)])
        if sline:
            print(f'- counts:  {sline}')
    else:
        print('- index:   out/CORE_SM29_INDEX/(missing)')


def main() -> None:
    os.chdir(ROOT)
    env = apply_determinism_env()
    run_cmd(python_cmd('-u', 'verify/static_core_safety_grep.py'), env=env)
    chunk_size = int(os.environ.get('CORE_SUITE_CHUNK_SIZE', '6'))
    core_overlay_off = os.environ.get('CORE_OVERLAY_OFF', '0')
    print('[core] clean out/')
    shutil.rmtree(ROOT / 'out', ignore_errors=True)
    (ROOT / 'out').mkdir(parents=True, exist_ok=True)
    run_suite_chunked('baseline', ROOT, env, chunk_size)
    neg_out_of_repo(env)
    neg_in_repo_overlay(env)
    neg_reference_glob(env)
    if core_overlay_off == '1':
        print('[core] overlay-off test (no in-place repo mutation)')
        run_suite_chunked_in_temp_repo('overlay_off', env, chunk_size)
        code = """
from pathlib import Path
import json
root = Path('.').resolve()
aud = root / 'out' / 'CORE_AUDIT'
def pick(label: str) -> Path:
    files = sorted(aud.glob(f'core_suite_run_v0_2_FULL_{label}_*.json'))
    if not files:
        raise SystemExit(f'FAIL: missing merged FULL report for {label}')
    return files[-1]
b = json.loads(pick('baseline').read_text(encoding='utf-8'))
o = json.loads(pick('overlay_off').read_text(encoding='utf-8'))
hb = (b.get('combined') or {}).get('semhash')
ho = (o.get('combined') or {}).get('semhash')
if not hb or not ho:
    raise SystemExit('FAIL: missing combined semhash in FULL report(s)')
if hb != ho:
    raise SystemExit(f'FAIL: suite semhash mismatch baseline vs overlay_off: {hb} != {ho}')
print(f'[core] suite semhash stable across overlay_off: {hb}')
"""
        run_cmd(python_cmd('-c', code), env=env)
    else:
        print('[core] overlay-off test: SKIP (set CORE_OVERLAY_OFF=1 to enable)')
    run_cmd(python_cmd('-u', 'verify/check_audit_open_scopes.py'), env=env)
    final_summary()


if __name__ == '__main__':
    main()
