#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Determinism knobs (avoid env-dependent drift)
export TZ="${TZ:-UTC}"
export PYTHONHASHSEED="${PYTHONHASHSEED:-0}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
export LANG="${LANG:-C.UTF-8}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"

CHUNK_SIZE="${COMPARE_SUITE_CHUNK_SIZE:-4}"

run_one_chunk() {
  local start="$1"
  local count="$2"

  local log rc outp
  set +e
  log="$(python3 00_TOP/TOOLS/run_compare_suite.py --start "${start}" --count "${count}" 2>&1)"
  rc=$?
  set -e
  echo "${log}" >&2
  outp="$(echo "${log}" | awk -F': ' '/^WROTE: /{print $2}' | tail -n 1)"
  echo "${outp}"
  return "${rc}"
}

run_suite_chunked() {
  echo "[compare] run suite [chunked size=${CHUNK_SIZE}]"

  local N_TOTAL
  N_TOTAL="$(python3 - <<'PY'
import sys
sys.path.insert(0, '00_TOP/TOOLS')
import run_compare_suite as m
print(len(getattr(m, 'COMPARE_ORDER', []) or []))
PY
)"
  if [ -z "${N_TOTAL}" ]; then
    echo "FAIL: could not determine COMPARE_ORDER length" >&2
    exit 2
  fi

  local chunk_paths=()
  local start=0
  while [ "${start}" -lt "${N_TOTAL}" ]; do
    local size="${CHUNK_SIZE}"
    local outp rc

    while true; do
      set +e
      outp="$(run_one_chunk "${start}" "${size}")"
      rc=$?
      set -e

      if [ -n "${outp}" ] && [ -f "${outp}" ] && [ "${rc}" -eq 0 ]; then
        break
      fi

      if [ "${size}" -le 1 ]; then
        echo "FAIL: compare suite chunk failed repeatedly at start=${start} (rc=${rc})" >&2
        exit 2
      fi
      size=$(( (size + 1) / 2 ))
      echo "[compare] retry chunk start=${start} with smaller count=${size}" >&2
    done

    chunk_paths+=("${outp}")

    local ran
    ran="$(python3 - <<PY
import json
from pathlib import Path
p = Path("${outp}")
obj = json.loads(p.read_text(encoding='utf-8'))
ch = obj.get('chunk') or {}
print(int(ch.get('ran') or 0))
PY
)"
    if [ -z "${ran}" ] || [ "${ran}" -le 0 ]; then
      echo "FAIL: could not read chunk.ran from ${outp}" >&2
      exit 2
    fi
    start=$((start + ran))
  done

  python3 -u verify/merge_compare_suite_chunks.py "${chunk_paths[@]}"
}

run_suite_chunked

python3 - <<'PY'
from pathlib import Path
import json

root = Path('.').resolve()

p = root/'out'/'COMPARE_AUDIT'
files = sorted(p.glob('compare_suite_run_v0_2_FULL_*.json'))
if not files:
    raise SystemExit('FAIL: no merged FULL compare_suite_run json found')
latest = files[-1]
obj = json.loads(latest.read_text(encoding='utf-8'))
counts = obj.get('counts') or {}
for key in ('MISSING','NONZERO'):
    if int(counts.get(key, 0)) != 0:
        raise SystemExit(f'FAIL: {key}={counts.get(key)} in {latest.name}')

idx_dir = root/'out'/'COMPARE_SM29_INDEX'
idx_files = sorted(idx_dir.glob('sm29_compare_index_v*.json'))
idx_latest = idx_files[-1] if idx_files else None

status_counts = {}
if idx_latest:
    data = json.loads(idx_latest.read_text(encoding='utf-8'))
    for e in data.get('entries', []):
        s = e.get('validation_status', 'UNKNOWN')
        status_counts[s] = status_counts.get(s, 0) + 1

print(f"COMPARE_VERIFY: PASS ({latest.name})")
print("\n[compare] where to look:")
print(f"- audit:   out/COMPARE_AUDIT/{latest.name}")
if idx_latest:
    md = idx_latest.with_suffix('.md')
    print(f"- index:   {idx_latest.as_posix()}")
    if md.exists():
        print(f"- indexmd: {md.as_posix()}")
    if status_counts:
        keys = ['AGREES','TENSION','COMPARED','UNTESTED','UNKNOWN']
        sline = ', '.join([f"{k}={status_counts.get(k,0)}" for k in keys if status_counts.get(k,0)])
        if sline:
            print(f"- counts:  {sline}")
else:
    print("- index:   out/COMPARE_SM29_INDEX/(missing)")
PY
