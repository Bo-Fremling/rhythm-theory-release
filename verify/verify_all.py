from __future__ import annotations

import os
import sys

from verify.verify_py_common import ROOT, apply_determinism_env, run_cmd, python_cmd


def main() -> None:
    os.chdir(ROOT)
    env = apply_determinism_env()
    run_cmd(python_cmd('-u', 'verify/verify_core.py'), env=env)
    cmp_rc = run_cmd(python_cmd('-u', 'verify/verify_compare.py'), env=env, check=False).returncode
    print('[match] generate SM29 data-match (overlay triage)')
    mat_rc = run_cmd(python_cmd('-u', '00_TOP/LOCKS/SM_PARAM_INDEX/sm29_data_match.py'), env=env, check=False).returncode
    if mat_rc != 0:
        print(f'[match] FAILED (exit={mat_rc}) — see out/SM_PARAM_INDEX/')
    print('[report] generate SM29 report + pages')
    run_cmd(python_cmd('-u', '00_TOP/LOCKS/SM_PARAM_INDEX/sm29_report.py'), env=env)
    if cmp_rc != 0:
        print(f'ALL_VERIFY: FAIL (compare exit={cmp_rc})')
        raise SystemExit(cmp_rc)
    if mat_rc != 0:
        print(f'ALL_VERIFY: FAIL (sm29_data_match exit={mat_rc})')
        raise SystemExit(mat_rc)
    print('ALL_VERIFY: PASS')


if __name__ == '__main__':
    main()
