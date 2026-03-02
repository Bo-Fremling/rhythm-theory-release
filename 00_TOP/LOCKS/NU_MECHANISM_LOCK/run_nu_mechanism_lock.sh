#!/usr/bin/env bash
set -euo pipefail
python3 00_TOP/LOCKS/NU_MECHANISM_LOCK/nu_mechanism_lock_run.py
python3 00_TOP/LOCKS/NU_MECHANISM_LOCK/nu_mechanism_lock_verify.py
