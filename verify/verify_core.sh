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

# Defense-in-depth: static grep for obvious bypass modules in *_coregen.py.
python3 -u verify/static_core_safety_grep.py

# Environments can terminate long single-process runs.
# The core suite runner supports deterministic chunking (--start/--count).
CHUNK_SIZE="${CORE_SUITE_CHUNK_SIZE:-6}"

# Optional strict mode: run a second full suite with OVERLAY physically absent.
# Default is OFF because the audit already forbids reading OVERLAY/*reference*.json,
# and some environments have tight wall-clock limits.
CORE_OVERLAY_OFF="${CORE_OVERLAY_OFF:-0}"


run_one_chunk() {
  local start="$1"
  local count="$2"

  # Capture stdout+stderr so we can parse WROTE even if the environment is strict.
  # We still echo the log to stderr for the human reviewer.
  local log rc outp
  set +e
  log="$(python3 00_TOP/TOOLS/run_core_no_facit_suite.py --start "${start}" --count "${count}" 2>&1)"
  rc=$?
  set -e
  echo "${log}" >&2
  outp="$(echo "${log}" | awk -F': ' '/^WROTE: /{print $2}' | tail -n 1)"
  echo "${outp}"
  return "${rc}"
}

run_suite_chunked() {
  local label="$1"
  echo "[core] run suite (${label}) [chunked size=${CHUNK_SIZE}]"

  local N_TOTAL
  N_TOTAL="$(python3 - <<'PY'
import sys
sys.path.insert(0, '00_TOP/TOOLS')
import run_core_no_facit_suite as m
print(len(getattr(m, 'COREGEN_ORDER', []) or []))
PY
)"
  if [ -z "${N_TOTAL}" ]; then
    echo "FAIL: could not determine COREGEN_ORDER length" >&2
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

      # Retry smaller if the chunk didn't complete.
      if [ "${size}" -le 1 ]; then
        echo "FAIL: core suite chunk failed repeatedly at start=${start} (rc=${rc})" >&2
        exit 2
      fi
      size=$(( (size + 1) / 2 ))
      echo "[core] retry chunk start=${start} with smaller count=${size}" >&2
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

  python3 -u verify/merge_core_suite_chunks.py --label "${label}" "${chunk_paths[@]}"
}

run_suite_chunked_in_temp_repo() {
  local label="$1"

  local tmp_repo
  tmp_repo="$(mktemp -d "${TMPDIR:-/tmp}/rt_verify_core_${label}.XXXXXXXX")"

  echo "[core] ${label}: create temp workcopy: ${tmp_repo}" >&2

  SRC_REPO="${ROOT}" DST_REPO="${tmp_repo}" python3 - <<'PY'
import os
import shutil
from pathlib import Path

src = Path(os.environ['SRC_REPO']).resolve()
dst = Path(os.environ['DST_REPO']).resolve()

ignore = shutil.ignore_patterns('out', '__pycache__', '*.pyc', '*.pyo', '.git', '.venv', 'venv')
shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore)

# Ensure overlay and reference files are truly absent in the temp workcopy.
ov = dst / '00_TOP' / 'OVERLAY'
if ov.exists():
    shutil.rmtree(ov)

for p in dst.rglob('*reference*.json'):
    try:
        p.unlink()
    except Exception:
        pass
PY

  # Reduce timestamp collisions with main-tree runs (stamp is second-resolution).
  sleep 1

  (
    cd "${tmp_repo}"

    local N_TOTAL
    N_TOTAL="$(python3 - <<'PY'
import sys
sys.path.insert(0, '00_TOP/TOOLS')
import run_core_no_facit_suite as m
print(len(getattr(m, 'COREGEN_ORDER', []) or []))
PY
)"

    local chunk_paths=()
    local start=0
    while [ "${start}" -lt "${N_TOTAL}" ]; do
      local size="${CHUNK_SIZE}"
      local outp rc

      while true; do
        local log
        set +e
        log="$(python3 00_TOP/TOOLS/run_core_no_facit_suite.py --start "${start}" --count "${size}" 2>&1)"
        rc=$?
        set -e
        echo "${log}" >&2
        outp="$(echo "${log}" | awk -F': ' '/^WROTE: /{print $2}' | tail -n 1)"

        if [ -n "${outp}" ] && [ -f "${outp}" ] && [ "${rc}" -eq 0 ]; then
          break
        fi

        if [ "${size}" -le 1 ]; then
          echo "FAIL: ${label} temp run chunk failed repeatedly at start=${start} (rc=${rc})" >&2
          exit 2
        fi
        size=$(( (size + 1) / 2 ))
        echo "[core] ${label} temp: retry chunk start=${start} with smaller count=${size}" >&2
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
        echo "FAIL: ${label} temp: could not read chunk.ran from ${outp}" >&2
        exit 2
      fi
      start=$((start + ran))
    done

    python3 -u verify/merge_core_suite_chunks.py --label "${label}" "${chunk_paths[@]}"
  )

  mkdir -p "${ROOT}/out/CORE_AUDIT"
  if [ -d "${tmp_repo}/out/CORE_AUDIT" ]; then
    cp -a "${tmp_repo}/out/CORE_AUDIT/"* "${ROOT}/out/CORE_AUDIT/" || true
  fi

  rm -rf "${tmp_repo}" || true
}

echo "[core] clean out/" 
rm -rf out
mkdir -p out

# Run once with overlay present (but protected by InfluenceAudit rules).
run_suite_chunked "baseline"

# NEG control: prove that InfluenceAudit forbids reading any out-of-repo file,
# even if a malicious Core tries to discover it under /tmp.
if [ -d "00_TOP/OVERLAY" ]; then
  SAMPLE="$(find 00_TOP/OVERLAY -type f 2>/dev/null | head -n 1 || true)"
  if [ -n "${SAMPLE}" ]; then
    NEG_TMP="$(mktemp "${TMPDIR:-/tmp}/rt_overlay_sample.XXXXXXXX")"
    cp "${SAMPLE}" "${NEG_TMP}" || true
    echo "[core] NEG: audit must forbid reading out-of-repo bait: ${NEG_TMP}" >&2
    python3 - <<PY
from pathlib import Path
import sys

sys.path.insert(0, '00_TOP/TOOLS')
from influence_audit import AuditConfig, InfluenceAudit, ForbiddenDependency

root = Path('.').resolve()
cfg = AuditConfig(repo_root=root)
target = Path(r'''${NEG_TMP}''').resolve()

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
PY
    rm -f "${NEG_TMP}" || true
  fi
fi


# NEG control (in-repo): audit must forbid opening anything under 00_TOP/OVERLAY
if [ -d "00_TOP/OVERLAY" ]; then
  SAMPLE2="$(find 00_TOP/OVERLAY -type f 2>/dev/null | head -n 1 || true)"
  if [ -n "${SAMPLE2}" ]; then
    echo "[core] NEG: audit must forbid opening in-repo OVERLAY file: ${SAMPLE2}" >&2
    python3 - <<PY
from pathlib import Path
import sys

sys.path.insert(0, "00_TOP/TOOLS")
from influence_audit import AuditConfig, InfluenceAudit, ForbiddenDependency

root = Path(".").resolve()
cfg = AuditConfig(repo_root=root)
target = (root / Path(r"${SAMPLE2}")).resolve()

try:
    with InfluenceAudit(cfg, capture_stack=False):
        Path(target).open("rb").read(1)
except ForbiddenDependency:
    print("[core] NEG: PASS (OVERLAY forbidden as expected)")
    raise SystemExit(0)
except Exception as e:
    print("[core] NEG: unexpected exception:", repr(e))
    raise SystemExit(2)

print("[core] NEG: FAIL (OVERLAY read was allowed)")
raise SystemExit(1)
PY
  fi
fi

# NEG control (glob): audit must forbid any *reference*.json even if placed under allowed roots.
NEG_REF="out/tmp_reference_test_reference.json"
mkdir -p out
printf "{"note":"neg test"}
" > "${NEG_REF}"
echo "[core] NEG: audit must forbid opening glob-matching reference file: ${NEG_REF}" >&2
python3 - <<PY
from pathlib import Path
import sys

sys.path.insert(0, "00_TOP/TOOLS")
from influence_audit import AuditConfig, InfluenceAudit, ForbiddenDependency

root = Path(".").resolve()
cfg = AuditConfig(repo_root=root)
target = (root / Path("out/tmp_reference_test_reference.json")).resolve()

try:
    with InfluenceAudit(cfg, capture_stack=False):
        Path(target).open("rb").read(1)
except ForbiddenDependency:
    print("[core] NEG: PASS (*reference*.json forbidden as expected)")
    raise SystemExit(0)
except Exception as e:
    print("[core] NEG: unexpected exception:", repr(e))
    raise SystemExit(2)

print("[core] NEG: FAIL (*reference*.json read was allowed)")
raise SystemExit(1)
PY
rm -f "${NEG_REF}" || true

# Run again with OVERLAY and *reference*.json physically absent (temp workcopy).
if [ "${CORE_OVERLAY_OFF}" = "1" ]; then
echo "[core] overlay-off test (no in-place repo mutation)" 
run_suite_chunked_in_temp_repo "overlay_off"

# Determinism/invariance: semhash must match between the two runs.
python3 - <<'PY'
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

print(f"[core] suite semhash stable across overlay_off: {hb}")
PY

else
  echo "[core] overlay-off test: SKIP (set CORE_OVERLAY_OFF=1 to enable)"
fi

# Defense-in-depth: all recorded opens should be either in-repo or system.
python3 -u verify/check_audit_open_scopes.py

python3 - <<'PY'
from pathlib import Path
import json

root = Path('.').resolve()
aud = root/'out'/'CORE_AUDIT'
files = sorted(aud.glob('core_suite_run_v0_2_FULL_overlay_off_*.json'))
if not files:
    files = sorted(aud.glob('core_suite_run_v0_2_FULL_baseline_*.json'))
if not files:
    raise SystemExit('FAIL: no merged FULL core suite report found (overlay_off or baseline)')
latest = files[-1]
obj = json.loads(latest.read_text(encoding='utf-8'))
counts = obj.get('counts') or {}
for key in ('FORBIDDEN','MISSING','TARGET_NONZERO','WRAPPER_ERROR'):
    if int(counts.get(key, 0)) != 0:
        raise SystemExit(f'FAIL: {key}={counts.get(key)} in {latest.name}')

idx_dir = root/'out'/'CORE_SM29_INDEX'
idx_files = sorted(idx_dir.glob('sm29_core_index_v*.json'))
idx_latest = idx_files[-1] if idx_files else None

status_counts = {}
if idx_latest:
    data = json.loads(idx_latest.read_text(encoding='utf-8'))
    for e in data.get('entries', []):
        s = e.get('derivation_status', 'UNKNOWN')
        status_counts[s] = status_counts.get(s, 0) + 1

print(f"CORE_VERIFY: PASS ({latest.name})")
print("\n[core] where to look:")
print(f"- audit:   out/CORE_AUDIT/{latest.name}")
if idx_latest:
    md = idx_latest.with_suffix('.md')
    print(f"- index:   {idx_latest.as_posix()}")
    if md.exists():
        print(f"- indexmd: {md.as_posix()}")
    if status_counts:
        keys = ['DERIVED','CANDIDATE-SET','HYP','BLANK','UNKNOWN']
        sline = ', '.join([f"{k}={status_counts.get(k,0)}" for k in keys if status_counts.get(k,0)])
        if sline:
            print(f"- counts:  {sline}")
else:
    print("- index:   out/CORE_SM29_INDEX/(missing)")
PY
