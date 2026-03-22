from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from verify.verify_py_common import (
    ROOT,
    apply_determinism_env,
    merge_json_args,
    module_len,
    parse_wrote,
    read_chunk_ran,
    run_cmd,
    python_cmd,
)


def run_one_chunk(start: int, count: int, env: dict) -> tuple[Path | None, int]:
    cp = run_cmd(
        python_cmd('00_TOP/TOOLS/run_compare_suite.py', '--start', str(start), '--count', str(count)),
        cwd=ROOT,
        env=env,
        check=False,
    )
    wrote = parse_wrote(cp.stdout + ('\n' + cp.stderr if cp.stderr else ''))
    return wrote, cp.returncode


def run_suite_chunked(env: dict, chunk_size: int) -> None:
    print(f'[compare] run suite [chunked size={chunk_size}]')
    n_total = module_len('run_compare_suite', 'COMPARE_ORDER', cwd=ROOT, env=env)
    chunk_paths: list[str] = []
    start = 0
    while start < n_total:
        size = chunk_size
        while True:
            outp, rc = run_one_chunk(start, size, env)
            if outp is not None and outp.exists() and rc == 0:
                break
            if size <= 1:
                raise SystemExit(f'FAIL: compare suite chunk failed repeatedly at start={start} (rc={rc})')
            size = (size + 1) // 2
            print(f'[compare] retry chunk start={start} with smaller count={size}', file=sys.stderr)
        chunk_paths.append(str(outp))
        ran = read_chunk_ran(outp)
        if ran <= 0:
            raise SystemExit(f'FAIL: could not read chunk.ran from {outp}')
        start += ran
    merge_json_args('verify/merge_compare_suite_chunks.py', chunk_paths, cwd=ROOT, env=env)


def final_summary() -> None:
    p = ROOT / 'out' / 'COMPARE_AUDIT'
    files = sorted(p.glob('compare_suite_run_v0_2_FULL_*.json'))
    if not files:
        raise SystemExit('FAIL: no merged FULL compare_suite_run json found')
    latest = files[-1]
    obj = json.loads(latest.read_text(encoding='utf-8'))
    counts = obj.get('counts') or {}
    for key in ('MISSING', 'NONZERO'):
        if int(counts.get(key, 0)) != 0:
            raise SystemExit(f'FAIL: {key}={counts.get(key)} in {latest.name}')
    idx_dir = ROOT / 'out' / 'COMPARE_SM29_INDEX'
    idx_files = sorted(idx_dir.glob('sm29_compare_index_v*.json'))
    idx_latest = idx_files[-1] if idx_files else None
    status_counts: dict[str, int] = {}
    if idx_latest:
        data = json.loads(idx_latest.read_text(encoding='utf-8'))
        for e in data.get('entries', []):
            s = e.get('validation_status', 'UNKNOWN')
            status_counts[s] = status_counts.get(s, 0) + 1
    print(f'COMPARE_VERIFY: PASS ({latest.name})')
    print('\n[compare] where to look:')
    print(f'- audit:   out/COMPARE_AUDIT/{latest.name}')
    if idx_latest:
        md = idx_latest.with_suffix('.md')
        print(f'- index:   {idx_latest.as_posix()}')
        if md.exists():
            print(f'- indexmd: {md.as_posix()}')
        keys = ['AGREES', 'TENSION', 'COMPARED', 'UNTESTED', 'UNKNOWN']
        sline = ', '.join([f'{k}={status_counts.get(k,0)}' for k in keys if status_counts.get(k,0)])
        if sline:
            print(f'- counts:  {sline}')
    else:
        print('- index:   out/COMPARE_SM29_INDEX/(missing)')


def main() -> None:
    os.chdir(ROOT)
    env = apply_determinism_env()
    chunk_size = int(os.environ.get('COMPARE_SUITE_CHUNK_SIZE', '4'))
    run_suite_chunked(env, chunk_size)
    final_summary()


if __name__ == '__main__':
    main()
