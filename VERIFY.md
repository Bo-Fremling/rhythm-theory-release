# Verification notes

**All run + read instructions live in `Release/START_HERE.md`.**

This page describes what is verified (and why), without duplicating the entry steps.

## What is actually tested

- **Core suite** runs under InfluenceAudit with overlay access blocked.
  - A valid Core run must report `FORBIDDEN = 0` in the audit summary.
  - Core selection/optimization must not depend on any overlay reference values.
  - Blocking is **prefix-based**: `00_TOP/OVERLAY*` (not only `00_TOP/OVERLAY/`).

- **Overlay-off test**: Core is additionally exercised with overlay temporarily removed.
  The verifier moves `00_TOP/OVERLAY` out-of-tree (random temp dir) so no readable
  in-repo copy exists during the test.

- **Compare suite** runs only after Core artifacts exist.
  - Compare is allowed to read overlay references and can compute comparisons,
    but must not change Core artifacts.

## Main reviewer artifacts

- Executive report: `00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_REPORT.md`
- Generated navigation page: `out/SM29_PAGES.md`

## Note on chunked execution (not weaker)

Some environments terminate long single-process runs. The Core suite runner
supports deterministic chunking. The verifier may run Core in multiple chunks
and then merges them into one **FULL** summary with explicit coverage checks.

- Control: `CORE_SUITE_CHUNK_SIZE=<N>` (default is conservative)
- Merged report: `out/CORE_AUDIT/core_suite_run_v0_2_FULL_*.json`
- The FULL report includes a stable suite-level semhash over
  `(script, status, exit_code, soft)` to ensure the chunking path is
  deterministically equivalent across runs.
