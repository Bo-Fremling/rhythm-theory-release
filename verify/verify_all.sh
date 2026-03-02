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

bash "$(dirname "${BASH_SOURCE[0]}")/verify_core.sh"

set +e
bash "$(dirname "${BASH_SOURCE[0]}")/verify_compare.sh"
CMP=$?
set -e

echo "[match] generate SM29 data-match (overlay triage)"
set +e
python3 -u 00_TOP/LOCKS/SM_PARAM_INDEX/sm29_data_match.py
MAT=$?
set -e
if [ "$MAT" -ne 0 ]; then
  echo "[match] FAILED (exit=$MAT) — see out/SM_PARAM_INDEX/"
fi

echo "[report] generate SM29 report + pages"
python3 -u 00_TOP/LOCKS/SM_PARAM_INDEX/sm29_report.py

if [ "$CMP" -ne 0 ]; then
  echo "ALL_VERIFY: FAIL (compare exit=$CMP)"
  exit "$CMP"
fi

if [ "$MAT" -ne 0 ]; then
  echo "ALL_VERIFY: FAIL (sm29_data_match exit=$MAT)"
  exit "$MAT"
fi

echo "ALL_VERIFY: PASS"
