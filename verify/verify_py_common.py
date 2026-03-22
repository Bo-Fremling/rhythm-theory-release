from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable, List

ROOT = Path(__file__).resolve().parent.parent
WROTE_RE = re.compile(r'^WROTE: (.+)$', re.MULTILINE)


def apply_determinism_env() -> dict:
    env = os.environ.copy()
    env.setdefault('TZ', 'UTC')
    env.setdefault('PYTHONHASHSEED', '0')
    env.setdefault('LC_ALL', 'C.UTF-8')
    env.setdefault('LANG', 'C.UTF-8')
    env.setdefault('OMP_NUM_THREADS', '1')
    env.setdefault('MKL_NUM_THREADS', '1')
    env.setdefault('OPENBLAS_NUM_THREADS', '1')
    env.setdefault('NUMEXPR_NUM_THREADS', '1')
    return env


def run_cmd(args: List[str], cwd: Path | None = None, env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
    cp = subprocess.run(args, cwd=str(cwd or ROOT), env=env, text=True, capture_output=True)
    if cp.stdout:
        print(cp.stdout, end='')
    if cp.stderr:
        print(cp.stderr, end='', file=sys.stderr)
    if check and cp.returncode != 0:
        raise SystemExit(cp.returncode)
    return cp


def python_cmd(*args: str) -> List[str]:
    return [sys.executable, *args]


def module_len(module_name: str, attr_name: str, cwd: Path | None = None, env: dict | None = None) -> int:
    code = (
        "import sys; "
        "sys.path.insert(0, '00_TOP/TOOLS'); "
        f"import {module_name} as m; "
        f"print(len(getattr(m, '{attr_name}', []) or []))"
    )
    cp = subprocess.run(python_cmd('-c', code), cwd=str(cwd or ROOT), env=env, text=True, capture_output=True)
    if cp.returncode != 0:
        if cp.stdout:
            print(cp.stdout, end='')
        if cp.stderr:
            print(cp.stderr, end='', file=sys.stderr)
        raise SystemExit(cp.returncode)
    return int(cp.stdout.strip())


def parse_wrote(output: str) -> Path | None:
    matches = WROTE_RE.findall(output)
    if not matches:
        return None
    p = Path(matches[-1].strip())
    return p if p.exists() else None


def read_chunk_ran(path: Path) -> int:
    obj = json.loads(path.read_text(encoding='utf-8'))
    return int((obj.get('chunk') or {}).get('ran') or 0)


def copytree_release(src: Path, dst: Path) -> None:
    ignore = shutil.ignore_patterns('out', '__pycache__', '*.pyc', '*.pyo', '.git', '.venv', 'venv')
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore)


def latest_file(pattern: str, base: Path) -> Path:
    files = sorted(base.glob(pattern))
    if not files:
        raise SystemExit(f'missing file for pattern: {pattern}')
    return files[-1]


def remove_overlay_and_references(repo_root: Path) -> None:
    ov = repo_root / '00_TOP' / 'OVERLAY'
    if ov.exists():
        shutil.rmtree(ov)
    for p in repo_root.rglob('*reference*.json'):
        try:
            p.unlink()
        except Exception:
            pass


def merge_json_args(script: str, extra_args: Iterable[str], cwd: Path | None = None, env: dict | None = None) -> None:
    run_cmd(python_cmd('-u', script, *list(extra_args)), cwd=cwd, env=env)
